import requests
import threading
import time
from typing import Any, Dict, List, Tuple
from app.plugins import _PluginBase
from app.core.event import eventmanager, Event
from app.schemas.types import EventType, MediaType
from app.db.subscribe_oper import SubscribeOper
from app.log import logger
from app.core.cache import Cache 

class CloudSub(_PluginBase):
    # 插件基本信息
    plugin_name = "同步订阅至CloudSub"
    plugin_desc = "将订阅变更信息实时推送到CloudSub服务器"
    plugin_icon = "https://raw.githubusercontent.com/timstarrr/MoviePilot-Plugins/refs/heads/main/icons/cloudsub.png"
    plugin_version = "1.0.2"
    plugin_author = "timstarrr"
    plugin_config_prefix = "cloudsub_"
    
    plugin_order = 20
    auth_level = 1

    # 配置属性初始化
    _enabled = False
    _remote_url = ""
    _api_key = ""
    _sync_add = True
    _sync_delete = True
    _sync_movie = True
    _sync_tv = True
    _sync_history = False
    
    # 缓存对象
    _cache = Cache(maxsize=100, ttl=60)

    def init_plugin(self, config: dict = None):
        self.subscribeoper = SubscribeOper()
        self.load_config(config)

        # 如果检测到开关开启，启动后台线程执行历史同步
        if self._sync_history:
            threading.Thread(target=self._run_history_sync, daemon=True).start()

    def load_config(self, config: dict):
        if config:
            self._enabled = config.get("enabled", False)
            self._remote_url = config.get("remote_url", "")
            self._api_key = config.get("api_key", "")
            self._sync_add = config.get("sync_add", True)
            self._sync_delete = config.get("sync_delete", True)
            self._sync_movie = config.get("sync_movie", True)
            self._sync_tv = config.get("sync_tv", True)
            # 加载历史同步开关
            self._sync_history = config.get("sync_history", False)

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
                                        }
                                    }
                                ]
                            },
                            # 在界面上添加“同步存量订阅”开关
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'sync_history',
                                            'label': '同步已有订阅',
                                            'hint': '开启并保存后，将立即同步所有现有订阅，完成后自动关闭',
                                            'persistent-hint': True
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 8},
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'remote_url',
                                            'label': '远程服务器地址',
                                            'placeholder': 'http://your-server.com/api/sync',
                                            'hint': '接收订阅数据的API接口地址',
                                            'persistent-hint': True,
                                            'rules': [{'required': True}]
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'api_key',
                                            'label': 'API Key',
                                            'type': 'password',
                                            'placeholder': '远程服务器验证密钥'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12},
                                'content': [{'component': 'div', 'text': '同步触发条件'}]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 6, 'md': 3},
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {'model': 'sync_add', 'label': '同步新增'}
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 6, 'md': 3},
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {'model': 'sync_delete', 'label': '同步删除'}
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 6, 'md': 3},
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {'model': 'sync_movie', 'label': '同步电影'}
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 6, 'md': 3},
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {'model': 'sync_tv', 'label': '同步剧集'}
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": False,
            "remote_url": "",
            "api_key": "",
            "sync_add": True,
            "sync_delete": True,
            "sync_movie": True,
            "sync_tv": True,
            "sync_history": False
        }

    def get_service(self) -> List[Dict[str, Any]]:
        return []

    def get_api(self):
        return []

    def get_page(self):
        pass
    
    def get_state(self) -> bool:
        return self._enabled

    def stop_service(self):
        pass

    # 历史同步的后台任务逻辑
    def _run_history_sync(self):
        logger.info("订阅同步：开始同步存量订阅...")
        try:
            # 1. 获取所有订阅
            all_subs = self.subscribeoper.list()
            total = len(all_subs)
            logger.info(f"订阅同步：发现 {total} 个订阅，准备发送...")

            # 2. 遍历发送
            for index, sub in enumerate(all_subs):
                # 转换成字典
                if hasattr(sub, "to_dict"):
                    sub_dict = sub.to_dict()
                else:
                    sub_dict = sub.__dict__
                
                # 调用核心发送逻辑
                self._process_sync("add", sub_dict)
                
                # 稍微歇一下，防止瞬间并发太高把服务器打挂
                time.sleep(0.5) 

            logger.info("订阅同步：存量订阅同步完成！")

        except Exception as e:
            logger.error(f"订阅同步：存量同步任务出错 - {str(e)}")
        finally:
            # 3. 任务完成后，自动关闭开关并保存配置
            self._sync_history = False
            self._save_config()

    def _save_config(self):
        """
        保存配置到数据库
        """
        config = {
            "enabled": self._enabled,
            "remote_url": self._remote_url,
            "api_key": self._api_key,
            "sync_add": self._sync_add,
            "sync_delete": self._sync_delete,
            "sync_movie": self._sync_movie,
            "sync_tv": self._sync_tv,
            "sync_history": self._sync_history
        }
        self.update_config(config)

    @eventmanager.register(EventType.SubscribeAdded)
    def handle_subscribe_added(self, event: Event):
        if not self._enabled or not self._sync_add:
            return

        event_data = event.event_data
        if not event_data:
            return

        try:
            sub_id = event_data.get("subscribe_id")
            sub_info = self.subscribeoper.get(sub_id)
            if not sub_info:
                return
            
            sub_dict = sub_info.to_dict()
            self._process_sync("add", sub_dict)

        except Exception as e:
            logger.error(f"订阅同步(新增)处理失败：{str(e)}")

    @eventmanager.register(EventType.SubscribeDeleted)
    def handle_subscribe_deleted(self, event: Event):
        if not self._enabled or not self._sync_delete:
            return

        event_data = event.event_data
        if not event_data:
            return

        try:
            sub_info = event_data.get("subscribe_info")
            if not sub_info:
                return

            self._process_sync("delete", sub_info)

        except Exception as e:
            logger.error(f"订阅同步(删除)处理失败：{str(e)}")

    def _process_sync(self, action: str, sub_info: dict):
        raw_type = sub_info.get("type")
        title = sub_info.get("name")
        year = sub_info.get("year")
        tmdb_id = sub_info.get("tmdbid")
        season = sub_info.get("season")

        if raw_type in ["电影", "Movie"]:
            media_type = "Movie"
        elif raw_type in ["电视剧", "TV"]:
            media_type = "TV"
        else:
            media_type = raw_type

        if media_type == "Movie":
            if not self._sync_movie:
                return
        elif media_type == "TV":
            if not self._sync_tv:
                return
        else:
            return
        
        cache_key = f"{action}_{media_type}_{tmdb_id}"
        if season:
             cache_key += f"_{season}"
        
        if self._cache.get(cache_key):
            # 对于存量同步，由于是手动触发，其实可以不走缓存，或者日志级别调低
            return
        
        self._cache.set(cache_key, True)

        payload = {
            "action": action,
            "api_key": self._api_key,
            "data": {
                "tmdb_id": tmdb_id,
                "type": media_type,
                "title": title,
                "year": year,
                "season": season if media_type == "TV" else None,
                "douban_id": sub_info.get("doubanid"),
                "total_episode": sub_info.get("total_episode"),
                "start_episode": sub_info.get("start_episode"),
            }
        }

        self._send_request(payload)

    def _send_request(self, payload: dict):
        if not self._remote_url:
            return

        try:
            logger.info(f"订阅同步：正在推送 {payload['data']['title']} ({payload['action']}) 到远程服务器")
            response = requests.post(
                self._remote_url, 
                json=payload, 
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            if response.status_code == 200:
                pass # 成功就不刷屏了
            else:
                logger.error(f"订阅同步：推送失败，HTTP状态码 {response.status_code}")
                
        except requests.RequestException as e:
            logger.error(f"订阅同步：网络请求异常 - {str(e)}")