# BookSpider

## 一.使用方法

### 1.依赖安装

Python版本>=3.9

```
pip install -r requirements.txt
```

### 2.运行命令行主程序

```
python3 main.py
```

### 3.指令介绍

1. setting:管理设置
2. spider:管理Spider
3. book:管理书籍
4. get:通过Url获取书籍
5. site:获取整站
6. commit:手动commit数据库
7. rollback:手动rollback数据库

## 二.架构简介

BookSpider主要分为以下模块：

1. Spider:负责信息的采集。用户可以通过继承Spider基类来实现自己的Spider。
2. Database:负责数据库访问
3. Manager:负责任务调度

## 三.Features & Todo

### 1.Features

* 数据库管理
* 命令行操作

### 2.Todo

* [ ] 优化commands里的命令
* [ ] 使用proxy_provider提供的代理
* [ ] 支持Epub导出
