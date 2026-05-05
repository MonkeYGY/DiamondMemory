from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy import create_engine
from config import DATABASE_URL

Base = declarative_base()

# 创建引擎
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

# 创建会话
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 依赖项
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 内容表
class Content(Base):
    __tablename__ = "contents"
    
    id = Column(String, primary_key=True, index=True)
    type = Column(String, index=True)  # file, url, video
    title = Column(String)
    path = Column(String)
    content_metadata = Column(JSON)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    
    # 关系
    tags = relationship("Tag", secondary="content_tags", back_populates="contents")

# 标签表
class Tag(Base):
    __tablename__ = "tags"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    
    # 关系
    contents = relationship("Content", secondary="content_tags", back_populates="tags")

# 内容标签关联表
class ContentTag(Base):
    __tablename__ = "content_tags"
    
    content_id = Column(String, ForeignKey("contents.id"), primary_key=True)
    tag_id = Column(Integer, ForeignKey("tags.id"), primary_key=True)

# 概念表
class Concept(Base):
    __tablename__ = "concepts"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    description = Column(Text)
    type = Column(String)
    created_at = Column(DateTime)

# 关系表
class Relationship(Base):
    __tablename__ = "relationships"
    
    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(String)
    target_id = Column(String)
    relation_type = Column(String)
    created_at = Column(DateTime)

# API密钥表
class APIKey(Base):
    __tablename__ = "api_keys"
    
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True)
    permissions = Column(JSON)
    created_at = Column(DateTime)
    expires_at = Column(DateTime)

# 创建所有表
Base.metadata.create_all(bind=engine)