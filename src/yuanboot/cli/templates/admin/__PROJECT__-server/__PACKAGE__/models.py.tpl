"""Persistent administration models and API field names."""

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import LONGTEXT, MEDIUMTEXT
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now():
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Audit:
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    is_deleted: Mapped[int] = mapped_column(Integer, default=0)
    create_by: Mapped[int] = mapped_column(Integer, default=0)
    create_name: Mapped[str] = mapped_column(String(50), default="")
    create_org_code: Mapped[str] = mapped_column(String(50), default="")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_by: Mapped[int] = mapped_column(Integer, default=0)
    update_name: Mapped[str] = mapped_column(String(50), default="")
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    def to_dict(self):
        result = {}
        for column in self.__table__.columns:
            if column.name in {"password", "token_version"}:
                continue
            parts = column.name.split("_")
            key = parts[0] + "".join(part.title() for part in parts[1:])
            value = getattr(self, column.name)
            result[key] = (
                value.replace(tzinfo=UTC).isoformat(timespec="seconds")
                if isinstance(value, datetime)
                else value
            )
        return result


class SysUser(Audit, Base):
    __tablename__ = "sys_user"
    username: Mapped[str] = mapped_column(String(50), default="", unique=True)
    password: Mapped[str] = mapped_column(String(100), default="")
    nickname: Mapped[str] = mapped_column(String(50), default="")
    email: Mapped[str] = mapped_column(String(100), default="")
    phone: Mapped[str] = mapped_column(String(20), default="")
    avatar: Mapped[str] = mapped_column(Text().with_variant(MEDIUMTEXT(), "mysql"), default="")
    dept_id: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[int] = mapped_column(Integer, default=1)
    is_admin: Mapped[int] = mapped_column(Integer, default=0)
    login_ip: Mapped[str] = mapped_column(String(50), default="")
    login_date: Mapped[datetime] = mapped_column(DateTime, default=now)
    token_version: Mapped[int] = mapped_column(Integer, default=0)


class SysRole(Audit, Base):
    __tablename__ = "sys_role"
    name: Mapped[str] = mapped_column(String(50), default="", unique=True)
    code: Mapped[str] = mapped_column(String(50), default="", unique=True)
    sort: Mapped[int] = mapped_column(Integer, default=1)
    data_scope: Mapped[int] = mapped_column(Integer, default=1)
    menu_check_strictly: Mapped[bool] = mapped_column(Boolean, default=True)
    dept_check_strictly: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[int] = mapped_column(Integer, default=1)
    remark: Mapped[str] = mapped_column(String(500), default="")


class SysMenu(Audit, Base):
    __tablename__ = "sys_menu"
    name: Mapped[str] = mapped_column(String(50), default="")
    parent_id: Mapped[int] = mapped_column(Integer, default=0)
    order_num: Mapped[int] = mapped_column(Integer, default=1)
    path: Mapped[str] = mapped_column(String(200), default="")
    component: Mapped[str] = mapped_column(String(255), default="")
    menu_type: Mapped[int] = mapped_column(Integer, default=0)
    visible: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[int] = mapped_column(Integer, default=1)
    icon: Mapped[str] = mapped_column(String(100), default="")
    is_frame: Mapped[int] = mapped_column(Integer, default=0)
    is_cache: Mapped[int] = mapped_column(Integer, default=0)
    permission: Mapped[str] = mapped_column(String(100), default="")
    query: Mapped[str] = mapped_column(String(255), default="")
    perms: Mapped[str] = mapped_column(String(100), default="")


class SysDept(Audit, Base):
    __tablename__ = "sys_dept"
    parent_id: Mapped[int] = mapped_column(Integer, default=0)
    path: Mapped[str] = mapped_column(String(200), default="")
    name: Mapped[str] = mapped_column(String(50), default="")
    sort: Mapped[int] = mapped_column(Integer, default=1)
    leader: Mapped[str] = mapped_column(String(50), default="")
    phone: Mapped[str] = mapped_column(String(20), default="")
    email: Mapped[str] = mapped_column(String(100), default="")
    status: Mapped[int] = mapped_column(Integer, default=1)


class SysUserRole(Audit, Base):
    __tablename__ = "sys_user_role"
    __table_args__ = (UniqueConstraint("user_id", "role_id"),)
    user_id: Mapped[int] = mapped_column(Integer, default=0)
    role_id: Mapped[int] = mapped_column(Integer, default=0)


class SysRoleMenu(Audit, Base):
    __tablename__ = "sys_role_menu"
    __table_args__ = (UniqueConstraint("role_id", "menu_id"),)
    role_id: Mapped[int] = mapped_column(Integer, default=0)
    menu_id: Mapped[int] = mapped_column(Integer, default=0)


class SysRoleDept(Audit, Base):
    __tablename__ = "sys_role_dept"
    __table_args__ = (UniqueConstraint("role_id", "dept_id"),)
    role_id: Mapped[int] = mapped_column(Integer, default=0)
    dept_id: Mapped[int] = mapped_column(Integer, default=0)


class SystemConfig(Audit, Base):
    __tablename__ = "system_config"
    config_key: Mapped[str] = mapped_column(String(100), default="", unique=True)
    config_value: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT(), "mysql"), default="")
    description: Mapped[str] = mapped_column(String(500), default="")
