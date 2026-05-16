/**
 * Per-agent accent colors for lists, tabs, and labels.
 */
(function (global) {
  const PALETTE = {
    claude: { color: "#e8956d", bg: "rgba(232, 149, 109, 0.12)" },
    codex: { color: "#3ecf8e", bg: "rgba(62, 207, 142, 0.12)" },
    gemini: { color: "#7baaf7", bg: "rgba(123, 170, 247, 0.12)" },
    cursor: { color: "#c084fc", bg: "rgba(192, 132, 252, 0.12)" },
    default: { color: "#8b949e", bg: "rgba(139, 148, 158, 0.08)" },
  };

  function agentKey(id) {
    const s = String(id || "").toLowerCase();
    if (s.includes("claude")) return "claude";
    if (s.includes("codex")) return "codex";
    if (s.includes("gemini")) return "gemini";
    if (s.includes("cursor")) return "cursor";
    return "default";
  }

  function getAgentStyle(id) {
    return PALETTE[agentKey(id)] || PALETTE.default;
  }

  function applyAgentColor(el, id) {
    if (!el) return getAgentStyle(id);
    const style = getAgentStyle(id);
    el.style.setProperty("--agent-color", style.color);
    el.style.setProperty("--agent-bg", style.bg);
    return style;
  }

  global.AgentRelayColors = { agentKey, getAgentStyle, applyAgentColor, PALETTE };
})(window);
