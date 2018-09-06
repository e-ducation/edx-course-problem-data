Problem API For CMS Xblock
=====

edx-course-problem-data is a simple Django app to retrieve XBlock data in Mongo.

Detailed documentation is in the "docs" directory.



## Install

进入虚拟环境，并切换到 edxapp 用户

```shell
vagrant ssh

sudo su edxapp

cd /edx/app/edxapp/edx-platform
```

拉取代码

```shell
git clone https://github.com/e-ducation/edx-course-problem-data.git
```

安装

```shell
pip install -e edx-course-problem-data
```

Quick start
-----------

1. Add "edx-course-problem-data" to your INSTALLED_APPS setting like this::

    INSTALLED_APPS = [
        ...
        'edx-course-problem-data',
    ]

2. Include the edx-course-problem-data URLconf in your project urls.py like this::

    path('exam/', include('edx-course-problem-data.urls')),
