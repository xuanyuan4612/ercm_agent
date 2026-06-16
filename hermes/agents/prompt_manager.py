"""
Prompt 管理器

YAML 模板驱动的 Prompt 管理，支持：
- 按 Agent/阶段加载对应模板
- 变量插值（案件信息、知识库上下文等）
- 版本化模板
- 热加载（通过 Redis 通知或 API 触发）
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from hermes.core.logging import get_logger

logger = get_logger(__name__)

# Prompt 模板目录 (位于 hermes/prompts/ 包根目录下)
PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"


class PromptManager:
    """Prompt 模板管理器

    模板文件存放于 agents/prompts/ 目录，按模块和阶段组织：
        prompts/
        ├── integrity/
        │   ├── intake.yaml
        │   ├── investigation.yaml
        │   └── ...
        ├── risk_monitor/
        └── common/
            └── system.yaml

    模板变量格式：{{ variable_name }}
    """

    def __init__(self) -> None:
        self._cache: dict[str, dict] = {}

    def load(self, module: str, stage: str) -> dict[str, str]:
        """加载指定模块和阶段的 Prompt 模板"""
        cache_key = f"{module}/{stage}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        template_path = PROMPT_DIR / module / f"{stage}.yaml"
        if not template_path.exists():
            logger.warning("prompt_template_not_found", path=str(template_path))
            return self._default_prompt(stage)

        try:
            with open(template_path, encoding="utf-8") as f:
                template = yaml.safe_load(f)
            self._cache[cache_key] = template
            return template
        except Exception as e:
            logger.error("prompt_load_failed", path=str(template_path), error=str(e))
            return self._default_prompt(stage)

    def render(
        self,
        module: str,
        stage: str,
        variables: dict[str, Any] | None = None,
    ) -> str:
        """加载模板并渲染

        Args:
            module: 模块名 (integrity/risk_monitor/...)
            stage: 阶段名 (intake/investigation/...)
            variables: 模板变量字典

        Returns:
            渲染后的完整 Prompt 文本
        """
        template = self.load(module, stage)
        variables = variables or {}

        system_prompt = template.get("system", "")
        user_prompt = template.get("user", "")

        # 变量插值
        for key, value in variables.items():
            placeholder = f"{{{{ {key} }}}}"
            system_prompt = system_prompt.replace(placeholder, str(value))
            user_prompt = user_prompt.replace(placeholder, str(value))

        # 注入知识库上下文
        kb_context = variables.get("kb_context", "")
        if kb_context:
            user_prompt = f"{user_prompt}\n\n{kb_context}"

        return (
            f"[System]\n{system_prompt}\n\n"
            f"[User]\n{user_prompt}"
        )

    def reload(self) -> None:
        """清空缓存，强制重新加载模板"""
        self._cache.clear()
        logger.info("prompt_cache_reloaded")

    @staticmethod
    def _default_prompt(stage: str) -> dict[str, str]:
        """默认 Prompt 模板（无 YAML 文件时回退）"""
        return {
            "system": (
                f"你是赫尔墨斯风控系统的 AI 助手，当前正在执行 {stage} 阶段的任务。"
                f"请根据提供的案件信息和知识库内容，给出专业、准确的分析。"
            ),
            "user": "案件信息：{{ case_info }}\n\n请根据以上信息开始分析。",
        }


# 全局单例
prompt_manager = PromptManager()
