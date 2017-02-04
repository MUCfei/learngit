#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#Models for user, blog, comment.

#uuid可生成唯一ID
import time, uuid

from orm import Model, StringField, BooleanField, FloatField, TextField

#生成一個唯一的ID作為數據庫表中每一行的主鍵
def next_id():
    return '%015d%s000' % (int(time.time() * 1000), uuid.uuid4().hex)

#用戶名的表
class User(Model):
    __table__ = 'users'

    id = StringField(primary_key=True, default=next_id, ddl='varchar(50)')
    email = StringField(ddl='varchar(50)')
    passwd = StringField(ddl='varchar(50)')
    admin = BooleanField() #身分，若為true則為管理員
    name = StringField(ddl='varchar(50)')
    image = StringField(ddl='varchar(500)') #頭像
    created_at = FloatField(default=time.time) #註冊時間

#部落格
class Blog(Model):
    __table__ = 'blogs'

    id = StringField(primary_key=True, default=next_id, ddl='varchar(50)')
    user_id = StringField(ddl='varchar(50)')
    user_name = StringField(ddl='varchar(50)')
    user_image = StringField(ddl='varchar(500)') #作者上傳的圖片
    name = StringField(ddl='varchar(50)') #文章名
    summary = StringField(ddl='varchar(200)') #文章概要
    content = TextField() #全文
    created_at = FloatField(default=time.time)

#評論
class Comment(Model):
    __table__ = 'comments'

    id = StringField(primary_key=True, default=next_id, ddl='varchar(50)')
    blog_id = StringField(ddl='varchar(50)')
    user_id = StringField(ddl='varchar(50)') #評論者ID
    user_name = StringField(ddl='varchar(50)')
    user_image = StringField(ddl='varchar(500)')
    content = TextField()
    created_at = FloatField(default=time.time)