#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'Michael Liao'

import asyncio, logging

import aiomysql
# SQL查詢語句
def log(sql, args=()):
    logging.info('SQL: %s' % sql)            
# 建立一個全局連接處，每個HTTP請求都從裡面獲得數據庫連接
async def create_pool(loop, **kw):
    logging.info('create database connection pool...')
	# 全局變數__pool，用於儲存整個連接處
    global __pool
    __pool = await aiomysql.create_pool(
		# **kw参数可以包含所有連接需要用到的關鍵字参數
		# 默認本機IP
        host=kw.get('host', 'localhost'),
        port=kw.get('port', 3306),
        user=kw['user'],
        password=kw['password'],
        db=kw['db'],
        charset=kw.get('charset', 'utf8'),
        autocommit=kw.get('autocommit', True),
		# 默認最大連接樹為10
        maxsize=kw.get('maxsize', 10),
        minsize=kw.get('minsize', 1),
		# 接收一個event_loop實例
        loop=loop
    )
# 封裝SQL SELECT語句為select函數
async def select(sql, args, size=None):
    log(sql, args)
    global __pool
    async with __pool.get() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
			# 執行SQL
			# SQL語句佔位符號為'?' MySQL的佔位符號為'%s'
            await cur.execute(sql.replace('?', '%s'), args or ())
			
			# 根據指定返回的size，返回查詢的结果
            if size:
				# 返回size查詢结果
                rs = await cur.fetchmany(size)
            else:
				# 返回所有查詢結果
                rs = await cur.fetchall()
        logging.info('rows returned: %s' % len(rs))
        return rs
# 封装INSERT, UPDATE, DELETE
# 語句操作参数一樣，所以定義一個通用的執行函数
# 返回操作影響的行號
async def execute(sql, args, autocommit=True):
    log(sql)
    async with __pool.get() as conn:
        if not autocommit:
            await conn.begin()
        try:
			# execute類型的SQL操作返回的结果只有行號，所以不需要用DictCursor
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql.replace('?', '%s'), args)
                affected = cur.rowcount
            if not autocommit:
                await conn.commit()
        except BaseException as e:
            if not autocommit:
                await conn.rollback()
            raise
        return affected

# 根據输入的參數生成占位符列表
def create_args_string(num):
    L = []
    for n in range(num):
        L.append('?')
	# 以','為分隔符號，將列表合成字符串
    return ', '.join(L)
# 定義Field類，負責保存(數據庫)表的字段名和字段類型
class Field(object):
	# 表的字段包含名字、類型、是否為表的主鍵和默認值
    def __init__(self, name, column_type, primary_key, default):
        self.name = name
        self.column_type = column_type
        self.primary_key = primary_key
        self.default = default
	# 當打印(數據庫)表時，输出(數據庫)表的信息:類名，字段類型和名字
    def __str__(self):
        return '<%s, %s:%s>' % (self.__class__.__name__, self.column_type, self.name)

# 定義不同類型的衍生Field
# 表的不同列的字段的類型不一樣

class StringField(Field):

    def __init__(self, name=None, primary_key=False, default=None, ddl='varchar(100)'):
        super().__init__(name, ddl, primary_key, default)

class BooleanField(Field):

    def __init__(self, name=None, default=False):
        super().__init__(name, 'boolean', False, default)

class IntegerField(Field):

    def __init__(self, name=None, primary_key=False, default=0):
        super().__init__(name, 'bigint', primary_key, default)

class FloatField(Field):

    def __init__(self, name=None, primary_key=False, default=0.0):
        super().__init__(name, 'real', primary_key, default)

class TextField(Field):

    def __init__(self, name=None, default=None):
        super().__init__(name, 'text', False, default)

# 定義Model的元類 
# 所有的元類都繼承自type
# ModelMetaclass元類定義了所有Model基類(繼承ModelMetaclass)的子類實現的操作 
# ModelMetaclass的工作主要是為一個數據庫表映射成一個封装的類做準備：
# ***類取具體子類(user)的映射信息
# 創造類的時候，排除對Model類的修改
# 在當前類中查找所有的類屬性(attrs)，如果找到Field屬性，就將其保存到__mappings__的dict中，同時從類屬性中删除Field(防止實例屬性遮住類的同名屬性)
# 將數據庫表名保存到__table__中 
# 完成這些工作就可以在Model中定義各種數據庫的操作方法

class ModelMetaclass(type):

	# __new__控制__init__的執行，所以在其執行之前
    # cls:代表要__init__的類，此参数在實例化时由Python解釋器自動提供(例如下文的User和Model)
    # bases：代表繼承父類的集合
    # attrs：類的方法集合

    def __new__(cls, name, bases, attrs):
	
		# 排除Model
        if name=='Model':
            return type.__new__(cls, name, bases, attrs)
			
		# 獲取table名词
        tableName = attrs.get('__table__', None) or name
        logging.info('found model: %s (table: %s)' % (name, tableName))
		
		# 獲取Field和主鍵名
        mappings = dict()
        fields = []
        primaryKey = None
        for k, v in attrs.items():
		
			# Field 屬性
            if isinstance(v, Field):
			
				# 此處打印的k是類的一个屬性，v是這個屬性在數據庫中對應的Field列表屬性
                logging.info('  found mapping: %s ==> %s' % (k, v))
                mappings[k] = v
				
				# 找到了主键
                if v.primary_key:
                  
					# 如果此時類實例的以存在主鍵，說明主鍵重複了  
                    if primaryKey:
                        raise StandardError('Duplicate primary key for field: %s' % k)
					
					 # 否則將此列設為列表的主鍵
                    primaryKey = k
                else:
                    fields.append(k)
					
		# end for
		
        if not primaryKey:
            raise StandardError('Primary key not found.')
			
		# 從類屬性中删除Field屬性
        for k in mappings.keys():
            attrs.pop(k)
		# 保存除主鍵外的屬性名為``（運算出字符串）列表形式
        escaped_fields = list(map(lambda f: '`%s`' % f, fields))
		# 保存属性和列的映射關係
        attrs['__mappings__'] = mappings 
		# 保存表名
        attrs['__table__'] = tableName
		# 保存主鍵屬性名
        attrs['__primary_key__'] = primaryKey 
		# 保存除主鍵外的屬性名
        attrs['__fields__'] = fields 
		
		# 構造默認的SELECT、INSERT、UPDATE、DELETE语句
        # ``反引號功能同repr()
        attrs['__select__'] = 'select `%s`, %s from `%s`' % (primaryKey, ', '.join(escaped_fields), tableName)
        attrs['__insert__'] = 'insert into `%s` (%s, `%s`) values (%s)' % (tableName, ', '.join(escaped_fields), primaryKey, create_args_string(len(escaped_fields) + 1))
        attrs['__update__'] = 'update `%s` set %s where `%s`=?' % (tableName, ', '.join(map(lambda f: '`%s`=?' % (mappings.get(f).name or f), fields)), primaryKey)
        attrs['__delete__'] = 'delete from `%s` where `%s`=?' % (tableName, primaryKey)
        return type.__new__(cls, name, bases, attrs)

# 定義ORM所有映射的基類：Model
# Model類的任意子類可以映射一个數據庫表
# Model類可以看作是對所有數據庫表操作的基本定義的映射
 
 
# 基於字典查詢形式
# Model從dict繼承，擁有字典的所有功能，同时實現特殊方法__getattr__和__setattr__，能够實現屬性操作
# 實現數據庫操作的所有方法，定義為class方法，所有繼承自Model都具有數據庫操作方法

class Model(dict, metaclass=ModelMetaclass):

    def __init__(self, **kw):
        super(Model, self).__init__(**kw)

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Model' object has no attribute '%s'" % key)

    def __setattr__(self, key, value):
        self[key] = value

    def getValue(self, key):
		# 内建函數getattr會自動處理
        return getattr(self, key, None)

    def getValueOrDefault(self, key):
        value = getattr(self, key, None)
        if value is None:
            field = self.__mappings__[key]
            if field.default is not None:
                value = field.default() if callable(field.default) else field.default
                logging.debug('using default value for %s: %s' % (key, str(value)))
                setattr(self, key, value)
        return value

    @classmethod
	# 類方法有類變量cls傳入，從而可以用cls做一些相關的處理。並且有子類繼承時，调用該類方法時，傳入的類變量cls是子類，而非父類。
    async def findAll(cls, where=None, args=None, **kw):
        ' find objects by where clause. '
		# sql語句不太會。。這裡好像是添加了参数 where、args、OrderBy、limit
        sql = [cls.__select__]
		# 如果有where参数就在sql语句中添加字符串where和参数where
        if where:
            sql.append('where')
            sql.append(where)
        if args is None:    # 这个参数是在执行sql语句前嵌入到sql语句中的，如果为None则定义一个空的list
            args = []
			
		# 如果有OrderBy参数就在sql语句中添加字符串OrderBy和参数OrderBy，但是OrderBy是在關鍵字参数中定義的
        orderBy = kw.get('orderBy', None)
        if orderBy:
            sql.append('order by')
            sql.append(orderBy)
        limit = kw.get('limit', None)
        if limit is not None:
            sql.append('limit')
            if isinstance(limit, int):
                sql.append('?')
                args.append(limit)
            elif isinstance(limit, tuple) and len(limit) == 2:
                sql.append('?, ?')
                args.extend(limit)
            else:
                raise ValueError('Invalid limit value: %s' % str(limit))
        rs = await select(' '.join(sql), args)
        return [cls(**r) for r in rs]
	
	# findNumber() - 根據WHERE條件查找，但返回的是整数，適用於select count(*)類型的SQL。
	
    @classmethod
    async def findNumber(cls, selectField, where=None, args=None):
        ' find number by select and where. '
        sql = ['select %s _num_ from `%s`' % (selectField, cls.__table__)]
        if where:
            sql.append('where')
            sql.append(where)
        rs = await select(' '.join(sql), args, 1)
        if len(rs) == 0:
            return None
        return rs[0]['_num_']

    @classmethod
    async def find(cls, pk):
        ' find object by primary key. '
        rs = await select('%s where `%s`=?' % (cls.__select__, cls.__primary_key__), [pk], 1)
        if len(rs) == 0:
            return None
        return cls(**rs[0])

    async def save(self):
        args = list(map(self.getValueOrDefault, self.__fields__))   # 將除主键外的屬性名添加到args這個列表中
        args.append(self.getValueOrDefault(self.__primary_key__))   # 再把主键添加到這個列表的最後
        rows = await execute(self.__insert__, args)
        if rows != 1:         # 插入紀錄受影響的行數應該為1，如果不是1 那就错了
            logging.warn('failed to insert record: affected rows: %s' % rows)
			# logging.warn("無法插入紀錄，受影響的行：%s" % rows)

    async def update(self):
        args = list(map(self.getValue, self.__fields__))
        args.append(self.getValue(self.__primary_key__))
        rows = await execute(self.__update__, args)
        if rows != 1:
            logging.warn('failed to update by primary key: affected rows: %s' % rows)

    async def remove(self):
        args = [self.getValue(self.__primary_key__)]
        rows = await execute(self.__delete__, args)
        if rows != 1:
            logging.warn('failed to remove by primary key: affected rows: %s' % rows)