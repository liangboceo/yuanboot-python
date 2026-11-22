"""Persistent administration models and API field names."""

from datetime import datetime, timezone


from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import LONGTEXT, MEDIUMTEXT
from sqlalchemy.orm import declarative_base

UTC = timezone.utc


def now():
    return datetime.now(UTC).replace(tzinfo=None)


Base = declarative_base()


class Audit:
    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    is_deleted = Column(Integer, default=0, nullable=False)
    create_by = Column(Integer, default=0, nullable=False)
    create_name = Column(String(50), default="", nullable=False)
    create_org_code = Column(String(50), default="", nullable=False)
    create_time = Column(DateTime, default=now, nullable=False)
    update_by = Column(Integer, default=0, nullable=False)
    update_name = Column(String(50), default="", nullable=False)
    update_time = Column(DateTime, default=now, onupdate=now, nullable=False)

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
    username = Column(String(50), default="", unique=True, nullable=False)
    password = Column(String(100), default="", nullable=False)
    nickname = Column(String(50), default="", nullable=False)
    email = Column(String(100), default="", nullable=False)
    phone = Column(String(20), default="", nullable=False)
    avatar = Column(Text().with_variant(MEDIUMTEXT(), "mysql"), default="", nullable=False)
    dept_id = Column(Integer, default=0, nullable=False)
    status = Column(Integer, default=1, nullable=False)
    is_admin = Column(Integer, default=0, nullable=False)
    login_ip = Column(String(50), default="", nullable=False)
    login_date = Column(DateTime, default=now, nullable=False)
    token_version = Column(Integer, default=0, nullable=False)


class SysRole(Audit, Base):
    __tablename__ = "sys_role"
    name = Column(String(50), default="", unique=True, nullable=False)
    code = Column(String(50), default="", unique=True, nullable=False)
    sort = Column(Integer, default=1, nullable=False)
    data_scope = Column(Integer, default=1, nullable=False)
    menu_check_strictly = Column(Boolean, default=True, nullable=False)
    dept_check_strictly = Column(Boolean, default=True, nullable=False)
    status = Column(Integer, default=1, nullable=False)
    remark = Column(String(500), default="", nullable=False)


class SysMenu(Audit, Base):
    __tablename__ = "sys_menu"
    name = Column(String(50), default="", nullable=False)
    parent_id = Column(Integer, default=0, nullable=False)
    order_num = Column(Integer, default=1, nullable=False)
    path = Column(String(200), default="", nullable=False)
    component = Column(String(255), default="", nullable=False)
    menu_type = Column(Integer, default=0, nullable=False)
    visible = Column(Integer, default=0, nullable=False)
    status = Column(Integer, default=1, nullable=False)
    icon = Column(String(100), default="", nullable=False)
    is_frame = Column(Integer, default=0, nullable=False)
    is_cache = Column(Integer, default=0, nullable=False)
    permission = Column(String(100), default="", nullable=False)
    query = Column(String(255), default="", nullable=False)
    perms = Column(String(100), default="", nullable=False)


class SysDept(Audit, Base):
    __tablename__ = "sys_dept"
    parent_id = Column(Integer, default=0, nullable=False)
    path = Column(String(200), default="", nullable=False)
    name = Column(String(50), default="", nullable=False)
    sort = Column(Integer, default=1, nullable=False)
    leader = Column(String(50), default="", nullable=False)
    phone = Column(String(20), default="", nullable=False)
    email = Column(String(100), default="", nullable=False)
    status = Column(Integer, default=1, nullable=False)


class SysUserRole(Audit, Base):
    __tablename__ = "sys_user_role"
    __table_args__ = (UniqueConstraint("user_id", "role_id"),)
    user_id = Column(Integer, default=0, nullable=False)
    role_id = Column(Integer, default=0, nullable=False)


class SysRoleMenu(Audit, Base):
    __tablename__ = "sys_role_menu"
    __table_args__ = (UniqueConstraint("role_id", "menu_id"),)
    role_id = Column(Integer, default=0, nullable=False)
    menu_id = Column(Integer, default=0, nullable=False)


class SysRoleDept(Audit, Base):
    __tablename__ = "sys_role_dept"
    __table_args__ = (UniqueConstraint("role_id", "dept_id"),)
    role_id = Column(Integer, default=0, nullable=False)
    dept_id = Column(Integer, default=0, nullable=False)


class SystemConfig(Audit, Base):
    __tablename__ = "system_config"
    config_key = Column(String(100), default="", unique=True, nullable=False)
    config_value = Column(Text().with_variant(LONGTEXT(), "mysql"), default="", nullable=False)
    description = Column(String(500), default="", nullable=False)
