import asyncio
import importlib
import inspect
import pkgutil
from typing import Any, Callable, Dict, List, Optional
from fastapi import APIRouter
import app.modules


def discover_tools() -> List[Dict[str, Any]]:
    """Auto-discover TOOLS from all subpackages in app.modules."""
    tools = []
    modules_pkg = app.modules
    for _, modname, ispkg in pkgutil.iter_modules(modules_pkg.__path__):
        if ispkg:
            tools_mod_name = f"app.modules.{modname}.tools"
            try:
                mod = importlib.import_module(tools_mod_name)
                if hasattr(mod, "TOOLS"):
                    module_tools = getattr(mod, "TOOLS")
                    if isinstance(module_tools, list):
                        tools.extend(module_tools)
            except ModuleNotFoundError:
                pass
    return tools


def discover_routers() -> List[APIRouter]:
    """Auto-discover APIRouter instances named `router` from app.modules."""
    routers = []
    modules_pkg = app.modules
    for _, modname, ispkg in pkgutil.iter_modules(modules_pkg.__path__):
        if ispkg:
            router_mod_name = f"app.modules.{modname}.router"
            try:
                mod = importlib.import_module(router_mod_name)
                if hasattr(mod, "router"):
                    router = getattr(mod, "router")
                    if isinstance(router, APIRouter):
                        routers.append(router)
            except ModuleNotFoundError:
                pass
    return routers


class ToolRegistry:
    def __init__(self):
        self._handlers: Dict[str, Callable[..., Any]] = {}
        self._schemas: List[Dict[str, Any]] = []
        self.reload()

    def reload(self):
        self._handlers.clear()
        self._schemas.clear()
        discovered = discover_tools()
        for item in discovered:
            if not isinstance(item, dict) or "function" not in item:
                continue
            fn_def = item["function"]
            name = fn_def.get("name")
            handler = item.get("handler")
            if name and handler:
                self._handlers[name] = handler
                # Schema sent to LLM should omit non-serializable handler
                schema = {
                    "type": item.get("type", "function"),
                    "function": fn_def
                }
                self._schemas.append(schema)

    def get_schemas(self) -> List[Dict[str, Any]]:
        return self._schemas

    def get_handler(self, tool_name: str) -> Optional[Callable[..., Any]]:
        return self._handlers.get(tool_name)

    async def execute_tool(self, tool_name: str, args: Dict[str, Any], **extra_kwargs) -> Any:
        handler = self.get_handler(tool_name)
        if not handler:
            raise ValueError(f"Tool '{tool_name}' is not registered.")

        sig = inspect.signature(handler)
        valid_kwargs = {}
        for param_name, param in sig.parameters.items():
            if param_name in args:
                valid_kwargs[param_name] = args[param_name]
            elif param_name in extra_kwargs:
                valid_kwargs[param_name] = extra_kwargs[param_name]

        if inspect.iscoroutinefunction(handler):
            return await handler(**valid_kwargs)
        else:
            return await asyncio.to_thread(handler, **valid_kwargs)


tool_registry = ToolRegistry()
