"""Transactional system management, RBAC and tree operations."""

import os
import re

from sqlalchemy import delete, func, or_, select

from yuanboot import Configuration
from yuanboot.hosting import HostedService

from .database import Database
from .models import (
    SysDept,
    SysMenu,
    SysRole,
    SysRoleDept,
    SysRoleMenu,
    SystemConfig,
    SysUser,
    SysUserRole,
    now,
)
from .security import Security, hash_password, strong_password

PUBLIC_CONFIG = {"system_name", "system_logo", "system_title", "system_description"}


def snake(name):
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def tree(items, *, labels=False):
    nodes = {item.id: {**item.to_dict(), "children": []} for item in items}
    for node in nodes.values():
        if labels:
            node["label"] = node["name"]
    roots = []
    for node in nodes.values():
        if node["parentId"] in nodes:
            nodes[node["parentId"]]["children"].append(node)
        else:
            roots.append(node)
    return roots


class SystemService:
    def __init__(self, database: Database):
        self.database = database

    def session(self):
        return self.database.sessions.begin()

    def get(self, session, model, identifier):
        item = session.get(model, identifier)
        if item is None or item.is_deleted:
            raise ValueError("记录不存在")
        return item

    def all(self, session, model):
        order = getattr(model, "order_num", getattr(model, "sort", model.id))
        return list(
            session.scalars(select(model).where(model.is_deleted == 0).order_by(order, model.id))
        )

    def roles(self, session, user):
        return list(
            session.scalars(
                select(SysRole)
                .join(SysUserRole, SysUserRole.role_id == SysRole.id)
                .where(SysUserRole.user_id == user.id, SysRole.is_deleted == 0, SysRole.status == 1)
            )
        )

    def menus(self, session, user):
        if user.is_admin:
            return [m for m in self.all(session, SysMenu) if m.status == 1]
        roles = self.roles(session, user)
        identifiers = session.scalars(
            select(SysRoleMenu.menu_id).where(SysRoleMenu.role_id.in_([r.id for r in roles]))
        )
        wanted = set(identifiers)
        all_menus = {m.id: m for m in self.all(session, SysMenu) if m.status == 1}
        # Include parent directories for selected leaves, without granting their permissions.
        selected = {i: all_menus[i] for i in wanted if i in all_menus}
        pending = list(selected.values())
        for item in pending:
            if item.parent_id in all_menus and item.parent_id not in selected:
                parent = all_menus[item.parent_id]
                selected[parent.id] = parent
                pending.append(parent)
        return sorted(selected.values(), key=lambda m: (m.parent_id, m.order_num, m.id))

    def permissions(self, session, user):
        if user.is_admin:
            return ["*:*:*"]
        roles = self.roles(session, user)
        assigned = set(
            session.scalars(
                select(SysRoleMenu.menu_id).where(SysRoleMenu.role_id.in_([r.id for r in roles]))
            )
        )
        return sorted(
            {
                value
                for item in self.all(session, SysMenu)
                if item.id in assigned and item.status == 1
                for value in (item.permission, item.perms)
                if value
            }
        )

    def authorize(self, session, user, permission):
        if not user.is_admin and permission not in self.permissions(session, user):
            raise PermissionError("没有操作权限")

    def user_info(self, session, user):
        data = user.to_dict()
        data.pop("tokenVersion", None)
        roles = self.roles(session, user)
        data.update(
            roleIds=[r.id for r in roles],
            roleNames=",".join(r.name for r in roles),
            roles=[r.code for r in roles],
            permissions=self.permissions(session, user),
        )
        dept = session.get(SysDept, user.dept_id) if user.dept_id else None
        data["deptName"] = dept.name if dept and not dept.is_deleted else ""
        return data

    def routes(self, session, user):
        menus = self.menus(session, user)
        auths = self.permissions(session, user)

        def build(parent, parent_path=""):
            result = []
            for item in menus:
                if item.parent_id != parent or item.menu_type == 2:
                    continue
                path = (
                    item.path
                    if item.path.startswith(("/", "http"))
                    else parent_path.rstrip("/") + "/" + item.path
                )
                route = {
                    "path": path,
                    "name": f"Menu{item.id}",
                    "meta": {
                        "title": item.name,
                        "icon": item.icon,
                        "isHide": item.visible == 1,
                        "showLink": item.visible == 0,
                        "isKeepAlive": item.is_cache == 1,
                        "keepAlive": item.is_cache == 1,
                        "menuType": item.menu_type,
                        "rank": item.order_num,
                        "auths": auths,
                    },
                }
                if item.menu_type in (1, 3):
                    route["component"] = item.component
                children = build(item.id, path)
                if children:
                    route["children"] = children
                    if item.menu_type == 0:
                        route["redirect"] = children[0]["path"]
                result.append(route)
            return result

        return build(0)

    def replace_links(self, session, model, owner_column, owner_id, value_column, values, target):
        if values is None:
            return
        identifiers = set(values)
        for identifier in identifiers:
            if identifier <= 0:
                raise ValueError("关联ID必须大于0")
            self.get(session, target, identifier)
        session.execute(delete(model).where(getattr(model, owner_column) == owner_id))
        session.add_all(
            [
                model(**{owner_column: owner_id, value_column: identifier})
                for identifier in identifiers
            ]
        )

    def check_parent(self, session, model, identifier, parent_id):
        visited = {identifier} if identifier else set()
        while parent_id:
            if parent_id in visited:
                raise ValueError("上级不能是自身或下级节点")
            visited.add(parent_id)
            parent_id = self.get(session, model, parent_id).parent_id

    def update(self, item, data, actor):
        for key, value in data.items():
            if key != "id":
                setattr(item, snake(key), value)
        if item.id:
            item.update_by, item.update_name, item.update_time = actor.id, actor.username, now()
        else:
            item.create_by, item.create_name = actor.id, actor.username
        return item

    def save_user(self, session, payload, actor):
        data = payload.model_dump()
        role_ids, password = data.pop("roleIds"), data.pop("password")
        item = self.get(session, SysUser, payload.id) if payload.id else SysUser()
        if payload.deptId:
            self.get(session, SysDept, payload.deptId)
        if item.id and item.is_admin and not actor.is_admin:
            raise PermissionError("不能修改超级管理员")
        if item.id:
            self.require_user_scope(session, actor, item.id)
        if item.id and item.is_admin and (payload.status == 0 or payload.username != item.username):
            raise ValueError("不能禁用或重命名超级管理员")
        self.update(item, data, actor)
        if password or not item.id:
            item.password = hash_password(password)
            item.token_version = (item.token_version or 0) + 1
        session.add(item)
        session.flush()
        self.replace_links(session, SysUserRole, "user_id", item.id, "role_id", role_ids, SysRole)
        return self.user_info(session, item)

    def save_role(self, session, payload, actor):
        data = payload.model_dump()
        menu_ids, dept_ids = data.pop("menuIds"), data.pop("deptIds")
        item = self.get(session, SysRole, payload.id) if payload.id else SysRole()
        if (
            item.id
            and item.code == "admin"
            and (
                payload.code != "admin"
                or payload.status != 1
                or menu_ids is not None
                or dept_ids is not None
            )
        ):
            raise ValueError("不能更改超级管理员角色权限")
        if payload.code == "admin" and (not item.id or item.code != "admin"):
            raise ValueError("admin 是保留角色编码")
        self.update(item, data, actor)
        session.add(item)
        session.flush()
        self.replace_links(session, SysRoleMenu, "role_id", item.id, "menu_id", menu_ids, SysMenu)
        self.replace_links(session, SysRoleDept, "role_id", item.id, "dept_id", dept_ids, SysDept)
        return item.to_dict()

    def save_tree(self, session, model, payload, actor):
        self.check_parent(session, model, payload.id, payload.parentId)
        item = self.get(session, model, payload.id) if payload.id else model()
        self.update(item, payload.model_dump(), actor)
        session.add(item)
        session.flush()
        if model is SysDept:
            parent = self.get(session, SysDept, item.parent_id) if item.parent_id else None
            item.path = (parent.path if parent else "") + f"/{item.id}"
        return item.to_dict()

    def remove(self, session, model, identifier, actor):
        item = self.get(session, model, identifier)
        if model is SysUser:
            self.require_user_scope(session, actor, identifier)
        if (model is SysUser and item.is_admin) or (model is SysRole and item.code == "admin"):
            raise ValueError("不能删除超级管理员")
        if model in (SysMenu, SysDept):
            if session.scalar(
                select(func.count())
                .select_from(model)
                .where(model.parent_id == identifier, model.is_deleted == 0)
            ):
                raise ValueError("存在子节点，无法删除")
        if model is SysDept and session.scalar(
            select(func.count())
            .select_from(SysUser)
            .where(SysUser.dept_id == identifier, SysUser.is_deleted == 0)
        ):
            raise ValueError("部门仍有关联用户")
        links = {
            SysUser: ((SysUserRole, "user_id"),),
            SysRole: ((SysUserRole, "role_id"), (SysRoleMenu, "role_id"), (SysRoleDept, "role_id")),
            SysMenu: ((SysRoleMenu, "menu_id"),),
            SysDept: ((SysRoleDept, "dept_id"),),
        }
        for relation, column in links[model]:
            session.execute(delete(relation).where(getattr(relation, column) == identifier))
        item.is_deleted = 1
        item.update_by, item.update_name = actor.id, actor.username
        if model is SysUser:
            item.token_version += 1

    def user_scope(self, session, actor):
        if actor.is_admin:
            return None
        roles = self.roles(session, actor)
        if any(r.data_scope == 1 for r in roles):
            return None
        dept_ids = set()
        for role in roles:
            if role.data_scope in (2, 3):
                dept_ids.add(actor.dept_id)
            if role.data_scope == 2:
                pending = [actor.dept_id]
                departments = self.all(session, SysDept)
                for parent in pending:
                    for dept in departments:
                        if dept.parent_id == parent and dept.id not in dept_ids:
                            dept_ids.add(dept.id)
                            pending.append(dept.id)
            if role.data_scope == 5:
                dept_ids.update(
                    session.scalars(
                        select(SysRoleDept.dept_id).where(SysRoleDept.role_id == role.id)
                    )
                )
        dept_ids.discard(0)
        return or_(SysUser.id == actor.id, SysUser.dept_id.in_(dept_ids))

    def require_user_scope(self, session, actor, identifier):
        scope = self.user_scope(session, actor)
        if scope is not None and not session.scalar(
            select(SysUser.id).where(SysUser.id == identifier, scope)
        ):
            raise PermissionError("无权访问该用户")

    def user_list(self, session, query, actor):
        statement = select(SysUser).where(SysUser.is_deleted == 0)
        scope = self.user_scope(session, actor)
        if scope is not None:
            statement = statement.where(scope)
        for field in ("username", "nickname", "phone"):
            if value := getattr(query, field):
                statement = statement.where(
                    getattr(SysUser, field).contains(value, autoescape=True)
                )
        if query.status not in (None, ""):
            statement = statement.where(SysUser.status == int(query.status))
        if query.deptId not in (None, ""):
            statement = statement.where(SysUser.dept_id == int(query.deptId))
        total = session.scalar(select(func.count()).select_from(statement.subquery()))
        users = session.scalars(
            statement.order_by(SysUser.id.desc())
            .offset((query.pageNum - 1) * query.pageSize)
            .limit(query.pageSize)
        )
        return {
            "list": [self.user_info(session, user) for user in users],
            "total": total,
            "page": query.pageNum,
        }


class SystemLifecycle(HostedService):
    def __init__(self, service: SystemService, configuration: Configuration, security: Security):
        self.service, self.configuration = service, configuration

    def start(self):
        config = self.configuration
        password = config.get_string("admin.initial_password", "admin123")
        if config.profile == "pro" and (
            not os.getenv("ADMIN_PASSWORD") or not strong_password(password)
        ):
            raise ValueError("pro requires a strong ADMIN_PASSWORD for initialization")
        with self.service.session() as session:
            admin = session.scalar(select(SysUser).where(SysUser.username == "admin"))
            if admin is None:
                admin = SysUser(
                    username="admin",
                    password=hash_password(password),
                    nickname="管理员",
                    status=1,
                    is_admin=1,
                )
                session.add(admin)
                session.flush()
            role = session.scalar(select(SysRole).where(SysRole.code == "admin"))
            if role is None:
                role = SysRole(name="超级管理员", code="admin", status=1)
                session.add(role)
                session.flush()
            seeds = [
                (1, "系统管理", 0, 1, "/system", "Layout", 0, "ri/settings-3-line"),
                (100, "用户管理", 1, 1, "user", "system/user/index", 1, "ep:avatar"),
                (101, "角色管理", 1, 2, "role", "system/role/index", 1, "ri/admin-line"),
                (102, "菜单管理", 1, 3, "menu", "system/menu/index", 1, "ep:menu"),
                (103, "部门管理", 1, 4, "dept", "system/dept/index", 1, "ep:fold"),
                (
                    107,
                    "系统配置",
                    1,
                    5,
                    "system-config",
                    "system/system-config/index",
                    1,
                    "ep:credit-card",
                ),
            ]
            for identifier, name, parent, order, path, component, kind, icon in seeds:
                if session.get(SysMenu, identifier) is None:
                    session.add(
                        SysMenu(
                            id=identifier,
                            name=name,
                            parent_id=parent,
                            order_num=order,
                            path=path,
                            component=component,
                            menu_type=kind,
                            icon=icon,
                            status=1,
                        )
                    )
            session.flush()
            if not session.scalar(
                select(SysUserRole.id).where(
                    SysUserRole.user_id == admin.id, SysUserRole.role_id == role.id
                )
            ):
                session.add(SysUserRole(user_id=admin.id, role_id=role.id))
            defaults = {
                "system_name": "Yuanboot Admin",
                "system_title": "Yuanboot Admin",
                "system_description": "基于 yuanboot-python 的后台管理系统",
                "system_logo": "",
            }
            for key, value in defaults.items():
                if not session.scalar(
                    select(SystemConfig.id).where(SystemConfig.config_key == key)
                ):
                    session.add(SystemConfig(config_key=key, config_value=value))
