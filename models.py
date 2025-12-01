"""
SQLAlchemy модели для таблицы properties.
Использует async SQLAlchemy 2.0 style с declarative_base.
"""
from sqlalchemy import Column, String, Date, BigInteger, Float, Boolean, Integer, DateTime, Text
from sqlalchemy.sql import func
from database import Base


class Property(Base):
    """
    Модель для таблицы properties.
    Представляет объект недвижимости с данными из двух Google Sheets.
    """
    __tablename__ = "properties"

    # Base fields (from SHEET_DEALS, read-only)
    crm_id = Column(String(50), primary_key=True, comment="Unique CRM identifier (PRIMARY KEY)")
    date_signed = Column(Date, nullable=True)
    contract_number = Column(String(100), nullable=True)
    mop = Column(String(100), nullable=True)
    rop = Column(String(100), nullable=True)
    dd = Column(String(100), nullable=True)
    client_name = Column(Text, nullable=True)
    address = Column(Text, nullable=True)
    complex = Column(String(200), nullable=True)
    contract_price = Column(BigInteger, nullable=True)
    expires = Column(Date, nullable=True)

    # Extra fields (from SHEET_PROGRESS, editable)
    category = Column(String(100), nullable=True)
    area = Column(Float, nullable=True)
    rooms_count = Column(Integer, nullable=True, comment="Количество комнат")
    krisha_price = Column(BigInteger, nullable=True)
    vitrina_price = Column(BigInteger, nullable=True)
    score = Column(Float, nullable=True)
    collage = Column(Boolean, default=False, nullable=False)
    prof_collage = Column(Boolean, default=False, nullable=False)
    krisha = Column(Text, nullable=True)
    instagram = Column(Text, nullable=True)
    tiktok = Column(Text, nullable=True)
    mailing = Column(Text, nullable=True)
    stream = Column(Text, nullable=True)
    shows = Column(Integer, default=0, nullable=False)
    analytics = Column(Boolean, default=False, nullable=False)
    price_update = Column(Text, nullable=True)
    provide_analytics = Column(Boolean, default=False, nullable=False)
    push_for_price = Column(Boolean, default=False, nullable=False)
    status = Column(String(100), default="Размещено", nullable=False)

    # Sync metadata
    last_modified_by = Column(String(10), default="SHEET", nullable=False, comment="Last change source: BOT or SHEET")
    last_modified_at = Column(DateTime(timezone=True), default=func.current_timestamp(), onupdate=func.current_timestamp(), nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.current_timestamp(), nullable=False)

    def __repr__(self):
        return f"<Property(crm_id='{self.crm_id}', complex='{self.complex}', address='{self.address}')>"


class ParsedProperty(Base):
    """
    Модель для таблицы parsed_properties.
    Представляет объекты недвижимости с Крыши.
    """
    __tablename__ = "parsed_properties"
    
    vitrina_id = Column(BigInteger, primary_key=True, autoincrement=True)
    rbd_id = Column(BigInteger, unique=True, nullable=False)
    krisha_id = Column(String(64), nullable=True)
    krisha_date = Column(DateTime(timezone=True), nullable=True)
    object_type = Column(String(255), nullable=True)
    address = Column(Text, nullable=True)
    complex = Column(String(255), nullable=True)
    builder = Column(String(255), nullable=True)
    flat_type = Column(String(255), nullable=True)
    property_class = Column(String(255), nullable=True)
    condition = Column(String(255), nullable=True)
    sell_price = Column(Float, nullable=True)
    sell_price_per_m2 = Column(Float, nullable=True)
    address_type = Column(String(255), nullable=True)
    house_num = Column(String(255), nullable=True)
    floor_num = Column(Integer, nullable=True)
    floor_count = Column(Integer, nullable=True)
    room_count = Column(Integer, nullable=True)
    phones = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    ceiling_height = Column(Float, nullable=True)
    area = Column(Float, nullable=True)
    year_built = Column(Integer, nullable=True)
    wall_type = Column(String(255), nullable=True)
    stats_agent_given = Column(String(255), nullable=True)
    stats_time_given = Column(DateTime(timezone=True), nullable=True)
    stats_object_status = Column(String(255), nullable=True)
    stats_recall_time = Column(DateTime(timezone=True), nullable=True)
    stats_description = Column(Text, nullable=True)
    stats_object_category = Column(String(10), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.current_timestamp(), onupdate=func.current_timestamp(), nullable=False)
    
    def __repr__(self):
        return f"<ParsedProperty(vitrina_id={self.vitrina_id}, complex='{self.complex}', address='{self.address}')>"
