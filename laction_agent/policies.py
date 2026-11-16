"""Tool allowlists enforced independently of provider-supplied tool calls."""

# No shell, writes, networking, delegation, cron mutation, memory or skill changes.
READ_ONLY_TOOLS = frozenset({
    "get_time", "list_tools", "agent_info", "device_health",
    "list_files", "read_file", "search_files", "rag_search", "apk_analyze",
})
