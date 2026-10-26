"""System API routes, compatible with the administration web application."""

import base64
import io
import logging

from fastapi import APIRouter, Body, Depends, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer
from PIL import Image, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from . import schemas as dto
from .models import SysDept, SysMenu, SysRole, SysRoleDept, SysRoleMenu, SystemConfig, SysUser, now
from .security import Security, hash_password, strong_password, verify_password
from .services import PUBLIC_CONFIG, SystemService, tree

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1", tags=["系统管理"])
bearer = HTTPBearer(auto_error=False)


class ApiError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def result(data=None, message="操作成功"):
    return {"status": True, "code": 200, "message": message, "data": data}


def actor(request, service, session, security):
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise ApiError(401, "请先登录")
    try:
        claims = security.decode(token)
        user = service.get(session, SysUser, int(claims["sub"]))
    except (PermissionError, ValueError) as exc:
        raise ApiError(401, "登录已失效，请重新登录") from exc
    if user.status != 1 or user.token_version != claims["ver"]:
        raise ApiError(401, "登录已失效，请重新登录")
    return user, claims


def register(paths, schema, permission, callback, *, public=False, methods=None):
    methods = methods or ["POST"]

    body_default = (
        ... if any(field.is_required() for field in schema.model_fields.values()) else None
    )

    def endpoint(
        request: Request, payload: schema = Body(default=body_default), credentials=Depends(bearer)
    ):
        payload = payload if payload is not None else schema()
        provider = request.state.services
        service = provider.get_service(SystemService)
        security = provider.get_service(Security)
        with service.session() as session:
            user, claims = (None, None) if public else actor(request, service, session, security)
            if permission:
                try:
                    service.authorize(session, user, permission)
                except PermissionError as exc:
                    raise ApiError(403, str(exc)) from exc
            return result(callback(request, payload, service, session, security, user, claims))

    endpoint.__name__ = callback.__name__
    for index, path in enumerate(paths):
        router.add_api_route(
            path, endpoint, methods=methods, name=callback.__name__, include_in_schema=index == 0
        )


def captcha(request, data, service, session, security, user, claims):
    ip = request.client.host if request.client else "unknown"
    if security.cache.increment("captcha-rate:" + ip, 60) > 60:
        raise ApiError(429, "请求过于频繁")
    return security.captcha()


def login(request, data, service, session, security, user, claims):
    ip = request.client.host if request.client else "unknown"
    key = "login-fail:" + ip + ":" + data.username.lower()
    if (security.cache.get(key) or 0) >= 5:
        raise ApiError(429, "登录失败次数过多，请稍后重试")
    security.check_captcha(data.captchaId, data.verifyCode)
    user = session.scalar(
        select(SysUser).where(SysUser.username == data.username, SysUser.is_deleted == 0)
    )
    if user is None or not verify_password(data.password, user.password) or user.status != 1:
        security.cache.increment(key, 300)
        raise ValueError("用户名、密码错误或账号已禁用")
    security.cache.delete(key)
    if not user.password.startswith("pbkdf2_sha256$"):
        user.password = hash_password(data.password)
    user.login_ip, user.login_date = ip, now()
    info = service.user_info(session, user)
    return {
        **security.tokens(user),
        **{key: info[key] for key in ("avatar", "username", "nickname", "roles", "permissions")},
    }


def refresh(request, data, service, session, security, user, claims):
    try:
        refresh_claims = security.consume_refresh(data.refreshToken)
        user = service.get(session, SysUser, refresh_claims["user"])
    except (PermissionError, ValueError) as exc:
        raise ApiError(401, "刷新令牌已失效") from exc
    if user.status != 1 or user.token_version != refresh_claims["ver"]:
        raise ApiError(401, "刷新令牌已失效")
    return security.tokens(user, refresh_claims["sid"])


def logout(request, data, service, session, security, user, claims):
    security.cache.delete("session:" + claims["sid"])


def user_info(request, data, service, session, security, user, claims):
    return service.user_info(session, user)


def routes(request, data, service, session, security, user, claims):
    return service.routes(session, user)


def user_list(request, data, service, session, security, user, claims):
    return service.user_list(session, data, user)


def user_detail(request, data, service, session, security, user, claims):
    scope = service.user_scope(session, user)
    if scope is not None and not session.scalar(
        select(SysUser.id).where(SysUser.id == data.id, scope)
    ):
        raise ApiError(403, "无权访问该用户")
    return service.user_info(session, service.get(session, SysUser, data.id))


def save_user(request, data, service, session, security, user, claims):
    service.authorize(session, user, "sys:user:edit" if data.id else "sys:user:add")
    return service.save_user(session, data, user)


def reset_password(request, data, service, session, security, user, claims):
    service.require_user_scope(session, user, data.id)
    target = service.get(session, SysUser, data.id)
    if target.is_admin and target.id != user.id:
        raise ApiError(403, "不能重置超级管理员密码")
    target.password, target.token_version = hash_password(data.password), target.token_version + 1
    target.update_by, target.update_name = user.id, user.username


def change_password(request, data, service, session, security, user, claims):
    if not verify_password(data.oldPassword, user.password):
        raise ValueError("旧密码错误")
    if not strong_password(data.newPassword):
        raise ValueError("新密码需包含大小写字母和特殊字符，长度不低于8位")
    user.password, user.token_version = hash_password(data.newPassword), user.token_version + 1
    security.cache.delete("session:" + claims["sid"])


def role_list(request, data, service, session, security, user, claims):
    query = select(SysRole).where(SysRole.is_deleted == 0)
    for key in ("name", "code"):
        if value := getattr(data, key):
            query = query.where(getattr(SysRole, key).contains(value, autoescape=True))
    if data.status not in (None, ""):
        query = query.where(SysRole.status == int(data.status))
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    items = session.scalars(
        query.order_by(SysRole.sort, SysRole.id)
        .offset((data.pageNum - 1) * data.pageSize)
        .limit(data.pageSize)
    )
    return {"list": [item.to_dict() for item in items], "total": total, "page": data.pageNum}


def all_roles(request, data, service, session, security, user, claims):
    return [item.to_dict() for item in service.all(session, SysRole) if item.status == 1]


def role_detail(request, data, service, session, security, user, claims):
    item = service.get(session, SysRole, data.id)
    return {
        "role": item.to_dict(),
        "menuIds": list(
            session.scalars(select(SysRoleMenu.menu_id).where(SysRoleMenu.role_id == item.id))
        ),
        "deptIds": list(
            session.scalars(select(SysRoleDept.dept_id).where(SysRoleDept.role_id == item.id))
        ),
    }


def save_role(request, data, service, session, security, user, claims):
    service.authorize(session, user, "sys:role:edit" if data.id else "sys:role:add")
    return service.save_role(session, data, user)


def role_menu(request, data, service, session, security, user, claims):
    item = service.get(session, SysRole, data.roleId)
    identifiers = (
        [m.id for m in service.all(session, SysMenu)]
        if item.code == "admin"
        else list(
            session.scalars(select(SysRoleMenu.menu_id).where(SysRoleMenu.role_id == item.id))
        )
    )
    return {"checkedKeys": identifiers, "menuList": tree(service.all(session, SysMenu))}


def menu_list(request, data, service, session, security, user, claims):
    items = service.all(session, SysMenu)
    if data.menuName:
        items = [item for item in items if data.menuName in item.name]
    if data.status is not None and data.status != "":
        items = [item for item in items if item.status == int(data.status)]
    return tree(items)


def menu_tree(request, data, service, session, security, user, claims):
    return tree(service.all(session, SysMenu), labels=True)


def menu_detail(request, data, service, session, security, user, claims):
    return service.get(session, SysMenu, data.id).to_dict()


def save_menu(request, data, service, session, security, user, claims):
    service.authorize(session, user, "sys:menu:edit" if data.id else "sys:menu:add")
    return service.save_tree(session, SysMenu, data, user)


def dept_list(request, data, service, session, security, user, claims):
    items = service.all(session, SysDept)
    if data.deptName:
        items = [item for item in items if data.deptName in item.name]
    if data.status not in (None, ""):
        items = [item for item in items if item.status == int(data.status)]
    return tree(items)


def dept_tree(request, data, service, session, security, user, claims):
    return tree(service.all(session, SysDept), labels=True)


def dept_detail(request, data, service, session, security, user, claims):
    return service.get(session, SysDept, data.id).to_dict()


def save_dept(request, data, service, session, security, user, claims):
    service.authorize(session, user, "sys:dept:edit" if data.id else "sys:dept:add")
    return service.save_tree(session, SysDept, data, user)


def get_config(request, data, service, session, security, user, claims):
    if data.configKey not in PUBLIC_CONFIG:
        user, _ = actor(request, service, session, security)
        service.authorize(session, user, "sys:config:query")
    item = session.scalar(
        select(SystemConfig).where(
            SystemConfig.config_key == data.configKey, SystemConfig.is_deleted == 0
        )
    )
    return (
        item.to_dict()
        if item
        else {"configKey": data.configKey, "configValue": "", "description": ""}
    )


def save_config(request, data, service, session, security, user, claims):
    item = session.scalar(select(SystemConfig).where(SystemConfig.config_key == data.configKey))
    item = item or SystemConfig()
    service.update(item, data.model_dump(), user)
    item.is_deleted = 0
    session.add(item)
    session.flush()
    return item.to_dict()


def remove(model):
    def delete_record(request, data, service, session, security, user, claims):
        service.remove(session, model, data.id, user)

    delete_record.__name__ = "delete_" + model.__tablename__
    return delete_record


register(["/sys/captcha"], dto.RequestModel, None, captcha, public=True)
register(["/sys/Login", "/sys/login"], dto.Login, None, login, public=True)
register(["/refresh-token"], dto.Refresh, None, refresh, public=True)
register(["/sys/Logout"], dto.RequestModel, None, logout)
register(["/sys/GetUserInfo", "/mine"], dto.RequestModel, None, user_info)
register(["/sys/GetRoutes"], dto.RequestModel, None, routes)
register(["/sys/user", "/sys/getUserList"], dto.ListQuery, "sys:user:list", user_list)
register(["/sys/user/detail", "/sys/getUserDetail"], dto.Identifier, "sys:user:query", user_detail)
register(["/sys/user/save", "/sys/saveUser"], dto.SaveUser, None, save_user)
register(["/sys/user/del", "/sys/delUser"], dto.Identifier, "sys:user:delete", remove(SysUser))
register(
    ["/sys/user/resetPwd", "/sys/resetPwd"], dto.ResetPassword, "sys:user:resetPwd", reset_password
)
register(["/sys/changePwd"], dto.ChangePassword, None, change_password)
register(["/sys/role", "/sys/getRoleList"], dto.ListQuery, "sys:role:list", role_list)
register(
    ["/sys/role/all", "/sys/getAllRoleList", "/sys/GetAllRoleList"],
    dto.RequestModel,
    "sys:role:list",
    all_roles,
)
register(["/sys/role/detail", "/sys/getRoleDetail"], dto.Identifier, "sys:role:query", role_detail)
register(["/sys/role/save", "/sys/saveRole"], dto.SaveRole, None, save_role)
register(["/sys/role/del", "/sys/delRole"], dto.Identifier, "sys:role:delete", remove(SysRole))
register(["/sys/role/menu", "/sys/getRoleMenu"], dto.RoleMenu, "sys:role:query", role_menu)
register(["/sys/menu", "/sys/getMenuList"], dto.MenuQuery, "sys:menu:list", menu_list)
register(
    ["/sys/menu/tree", "/sys/getMenuTree", "/sys/GetMenuTree"],
    dto.RequestModel,
    "sys:menu:list",
    menu_tree,
)
register(["/sys/menu/detail", "/sys/getMenuDetail"], dto.Identifier, "sys:menu:query", menu_detail)
register(["/sys/menu/save", "/sys/saveMenu"], dto.SaveMenu, None, save_menu)
register(["/sys/menu/del", "/sys/delMenu"], dto.Identifier, "sys:menu:delete", remove(SysMenu))
register(["/sys/dept", "/sys/getDeptList"], dto.DeptQuery, "sys:dept:list", dept_list)
register(
    ["/sys/dept/tree", "/sys/getDeptTree", "/sys/GetDeptTree"],
    dto.RequestModel,
    "sys:dept:list",
    dept_tree,
)
register(["/sys/dept/detail", "/sys/getDeptDetail"], dto.Identifier, "sys:dept:query", dept_detail)
register(["/sys/dept/save", "/sys/saveDept"], dto.SaveDept, None, save_dept)
register(["/sys/dept/del", "/sys/delDept"], dto.Identifier, "sys:dept:delete", remove(SysDept))
register(["/sys/GetSystemConfig"], dto.ConfigKey, None, get_config, public=True)
register(["/sys/SaveSystemConfig"], dto.SaveConfig, "sys:config:edit", save_config)


@router.get("/mine")
def mine(request: Request, credentials=Depends(bearer)):
    service = request.state.services.get_service(SystemService)
    security = request.state.services.get_service(Security)
    with service.session() as session:
        user, _ = actor(request, service, session, security)
        return result(service.user_info(session, user))


@router.get("/mine-logs")
def mine_logs(request: Request, credentials=Depends(bearer)):
    service = request.state.services.get_service(SystemService)
    security = request.state.services.get_service(Security)
    with service.session() as session:
        user, _ = actor(request, service, session, security)
        return result(
            {
                "list": [
                    {
                        "id": user.id,
                        "loginIp": user.login_ip,
                        "createTime": user.login_date.isoformat(),
                        "message": "最近一次登录",
                    }
                ],
                "total": 1,
            }
        )


@router.post("/sys/UploadUserAvatar")
def upload_avatar(request: Request, file: UploadFile = File(...), credentials=Depends(bearer)):
    service = request.state.services.get_service(SystemService)
    security = request.state.services.get_service(Security)
    with service.session() as session:
        user, _ = actor(request, service, session, security)
        raw = file.file.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("头像不能超过2MB")
        try:
            image = Image.open(io.BytesIO(raw))
            if image.width * image.height > 16000000:
                raise ValueError("图片尺寸过大")
            image.load()
            image.thumbnail((512, 512))
            output = io.BytesIO()
            image.convert("RGB").save(output, format="JPEG", quality=85)
        except (UnidentifiedImageError, OSError) as exc:
            raise ValueError("请上传有效图片") from exc
        avatar = "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode()
        user.avatar = avatar
        return result({"avatar": avatar})


def configure_errors(app):
    async def error(request, exc):
        status = (
            exc.status
            if isinstance(exc, ApiError)
            else 403
            if isinstance(exc, PermissionError)
            else 422
            if isinstance(exc, RequestValidationError)
            else 200
        )
        message = (
            "请求参数不正确"
            if isinstance(exc, RequestValidationError)
            else "数据重复或仍有关联记录"
            if isinstance(exc, IntegrityError)
            else exc.message
            if isinstance(exc, ApiError)
            else str(exc)
        )
        return JSONResponse(
            {
                "status": False,
                "code": status if status != 200 else 500,
                "message": message,
                "data": None,
            },
            status_code=status,
        )

    for kind in (ApiError, ValueError, PermissionError, RequestValidationError, IntegrityError):
        app.add_exception_handler(kind, error)
