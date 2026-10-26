"""Validated request contracts with the administration UI's camelCase field names."""

from pydantic import BaseModel, ConfigDict, Field


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_max_length=4096)


class Login(RequestModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=256)
    captchaId: str = Field(min_length=1, max_length=128)
    verifyCode: str = Field(min_length=1, max_length=16)


class Identifier(RequestModel):
    id: int = Field(gt=0)


class ListQuery(RequestModel):
    pageNum: int = Field(default=1, ge=1)
    pageSize: int = Field(default=20, ge=1, le=200)
    username: str = ""
    nickname: str = ""
    phone: str = ""
    name: str = ""
    code: str = ""
    status: str | int | None = ""
    deptId: str | int | None = ""


class SaveUser(RequestModel):
    id: int = Field(default=0, ge=0)
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(default="", max_length=256)
    nickname: str = Field(default="", max_length=50)
    email: str = Field(default="", max_length=100)
    phone: str = Field(default="", max_length=20)
    avatar: str = Field(default="", max_length=3000000)
    deptId: int = Field(default=0, ge=0)
    status: int = Field(default=1, ge=0, le=1)
    roleIds: list[int] | None = None


class ResetPassword(Identifier):
    password: str = Field(min_length=1, max_length=256)


class ChangePassword(RequestModel):
    oldPassword: str = Field(min_length=1, max_length=256)
    newPassword: str = Field(min_length=8, max_length=256)


class SaveRole(RequestModel):
    id: int = Field(default=0, ge=0)
    name: str = Field(min_length=1, max_length=50)
    code: str = Field(min_length=1, max_length=50)
    sort: int = 1
    status: int = Field(default=1, ge=0, le=1)
    remark: str = Field(default="", max_length=500)
    dataScope: int = Field(default=1, ge=1, le=5)
    menuCheckStrictly: bool = True
    deptCheckStrictly: bool = True
    menuIds: list[int] | None = None
    deptIds: list[int] | None = None


class RoleMenu(RequestModel):
    roleId: int = Field(gt=0)


class MenuQuery(RequestModel):
    menuName: str = ""
    status: str | int | None = None


class SaveMenu(RequestModel):
    id: int = Field(default=0, ge=0)
    name: str = Field(min_length=1, max_length=50)
    parentId: int = Field(default=0, ge=0)
    orderNum: int = 1
    path: str = Field(default="", max_length=200)
    component: str = Field(default="", max_length=255)
    menuType: int = Field(default=1, ge=0, le=3)
    visible: int = Field(default=0, ge=0, le=1)
    status: int = Field(default=1, ge=0, le=1)
    icon: str = Field(default="", max_length=100)
    isFrame: int = Field(default=0, ge=0, le=1)
    isCache: int = Field(default=0, ge=0, le=1)
    permission: str = Field(default="", max_length=100)
    perms: str = Field(default="", max_length=100)
    query: str = Field(default="", max_length=255)


class DeptQuery(RequestModel):
    deptName: str = ""
    status: str | int | None = ""


class SaveDept(RequestModel):
    id: int = Field(default=0, ge=0)
    parentId: int = Field(default=0, ge=0)
    name: str = Field(min_length=1, max_length=50)
    sort: int = 1
    leader: str = Field(default="", max_length=50)
    phone: str = Field(default="", max_length=20)
    email: str = Field(default="", max_length=100)
    status: int = Field(default=1, ge=0, le=1)


class ConfigKey(RequestModel):
    configKey: str = Field(min_length=1, max_length=100)


class SaveConfig(ConfigKey):
    configValue: str = Field(max_length=3000000)
    description: str = Field(default="", max_length=500)


class Refresh(RequestModel):
    refreshToken: str = Field(min_length=1, max_length=256)
