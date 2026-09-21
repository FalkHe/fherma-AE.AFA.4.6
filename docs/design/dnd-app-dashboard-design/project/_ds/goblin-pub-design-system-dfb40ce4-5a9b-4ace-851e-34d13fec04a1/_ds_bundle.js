/* @ds-bundle: {"format":4,"namespace":"GoblinPubDesignSystem_dfb40c","components":[{"name":"ChatComposer","sourcePath":"components/chat/ChatComposer.jsx"},{"name":"ChatMessage","sourcePath":"components/chat/ChatMessage.jsx"},{"name":"DiceRoll","sourcePath":"components/chat/DiceRoll.jsx"},{"name":"TypingIndicator","sourcePath":"components/chat/TypingIndicator.jsx"},{"name":"Badge","sourcePath":"components/core/Badge.jsx"},{"name":"Button","sourcePath":"components/core/Button.jsx"},{"name":"Card","sourcePath":"components/core/Card.jsx"},{"name":"Dialog","sourcePath":"components/core/Dialog.jsx"},{"name":"Divider","sourcePath":"components/core/Divider.jsx"},{"name":"Icon","sourcePath":"components/core/Icon.jsx"},{"name":"IconButton","sourcePath":"components/core/IconButton.jsx"},{"name":"Tag","sourcePath":"components/core/Tag.jsx"},{"name":"Checkbox","sourcePath":"components/forms/Checkbox.jsx"},{"name":"Field","sourcePath":"components/forms/Field.jsx"},{"name":"Input","sourcePath":"components/forms/Input.jsx"},{"name":"Select","sourcePath":"components/forms/Select.jsx"},{"name":"Switch","sourcePath":"components/forms/Switch.jsx"},{"name":"Textarea","sourcePath":"components/forms/Textarea.jsx"},{"name":"AbilityScore","sourcePath":"components/game/AbilityScore.jsx"},{"name":"PlayerStatCard","sourcePath":"components/game/PlayerStatCard.jsx"},{"name":"ResourceBar","sourcePath":"components/game/ResourceBar.jsx"},{"name":"SceneImage","sourcePath":"components/game/SceneImage.jsx"}],"sourceHashes":{"components/chat/ChatComposer.jsx":"cdc181c9eb83","components/chat/ChatMessage.jsx":"8311b9c3631d","components/chat/DiceRoll.jsx":"e317fc30e0ff","components/chat/TypingIndicator.jsx":"63780b36458f","components/core/Badge.jsx":"247949b4046d","components/core/Button.jsx":"a37134f8ff6d","components/core/Card.jsx":"ba3b483295c4","components/core/Dialog.jsx":"ede1cd5b5c46","components/core/Divider.jsx":"9458b5908072","components/core/Icon.jsx":"bd4e5ebf5d82","components/core/IconButton.jsx":"169cc9f3e64c","components/core/Tag.jsx":"0c0e4ab314b3","components/forms/Checkbox.jsx":"f8e6d3df8156","components/forms/Field.jsx":"a6c85c9dd86b","components/forms/Input.jsx":"cb33d5fe0932","components/forms/Select.jsx":"757584a217ff","components/forms/Switch.jsx":"24af180f6327","components/forms/Textarea.jsx":"6014238a70b7","components/game/AbilityScore.jsx":"2a307ca9d50f","components/game/PlayerStatCard.jsx":"d8f153cd17d9","components/game/ResourceBar.jsx":"988828d813eb","components/game/SceneImage.jsx":"9c36d64e7b38","mui/goblinPubTheme.js":"598f7773a946","ui_kits/goblin-pub-app/AppShell.jsx":"497cb94eae3c","ui_kits/goblin-pub-app/CampaignHome.jsx":"12fb5cbfeaba","ui_kits/goblin-pub-app/CharacterSheet.jsx":"75116e99afc9","ui_kits/goblin-pub-app/NewSessionDialog.jsx":"d0afd276eedc","ui_kits/goblin-pub-app/SessionView.jsx":"0415c044618b","ui_kits/goblin-pub-app/data.jsx":"92dbd5b48a07"},"inlinedExternals":[],"unexposedExports":[{"name":"goblinPubThemeOptions","sourcePath":"mui/goblinPubTheme.js"},{"name":"goblinPubTokens","sourcePath":"mui/goblinPubTheme.js"}]} */

(() => {

const __ds_ns = (window.GoblinPubDesignSystem_dfb40c = window.GoblinPubDesignSystem_dfb40c || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// components/chat/TypingIndicator.jsx
try { (() => {
function TypingIndicator({
  label = "The Dungeon Master is thinking",
  style
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: "var(--sp-4)",
      padding: "8px 16px",
      borderRadius: "var(--radius-pill)",
      background: "var(--surface-card)",
      border: "1px solid var(--border-soft)",
      ...style
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: "inline-flex",
      gap: 5
    }
  }, [0, 1, 2].map(i => /*#__PURE__*/React.createElement("span", {
    key: i,
    style: {
      width: 6,
      height: 6,
      borderRadius: "50%",
      background: "var(--lantern-400)",
      animation: `gp-flicker 1.4s ${i * 0.18}s infinite var(--ease-standard)`
    }
  }))), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-smallcaps)",
      fontSize: "var(--text-micro)",
      letterSpacing: ".08em",
      color: "var(--text-muted)"
    }
  }, label), /*#__PURE__*/React.createElement("style", null, "@keyframes gp-flicker{0%,100%{opacity:.25;transform:translateY(0)}45%{opacity:1;transform:translateY(-2px)}}"));
}
Object.assign(__ds_scope, { TypingIndicator });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/chat/TypingIndicator.jsx", error: String((e && e.message) || e) }); }

// components/core/Card.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const TONES = {
  default: {
    background: "var(--surface-card)",
    border: "1px solid var(--border-soft)"
  },
  raised: {
    background: "var(--surface-raised)",
    border: "1px solid var(--border-soft)",
    boxShadow: "var(--shadow-md)"
  },
  timber: {
    background: "var(--surface-timber)",
    border: "1px solid var(--border-timber)",
    boxShadow: "var(--shadow-md)"
  },
  sunken: {
    background: "var(--surface-inset)",
    border: "1px solid var(--border-hairline)"
  }
};
function Card({
  children,
  tone = "default",
  lantern = false,
  organic = true,
  padding = "var(--sp-6)",
  title,
  action,
  style,
  ...rest
}) {
  return /*#__PURE__*/React.createElement("section", _extends({}, rest, {
    style: {
      position: "relative",
      borderRadius: organic ? "var(--radius-organic)" : "var(--radius-lg)",
      padding,
      backgroundImage: lantern ? "var(--wash-lantern)" : undefined,
      color: "var(--text-primary)",
      ...TONES[tone],
      ...style
    }
  }), (title || action) && /*#__PURE__*/React.createElement("header", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      gap: "var(--sp-4)",
      marginBottom: "var(--sp-4)"
    }
  }, /*#__PURE__*/React.createElement("h3", {
    style: {
      font: "var(--weight-bold) var(--text-h3)/var(--lh-h3) var(--font-display)",
      margin: 0
    }
  }, title), action), children);
}
Object.assign(__ds_scope, { Card });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Card.jsx", error: String((e && e.message) || e) }); }

// components/core/Divider.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function Divider({
  label,
  style,
  ...rest
}) {
  if (!label) return /*#__PURE__*/React.createElement("hr", _extends({}, rest, {
    style: {
      border: 0,
      height: 1,
      background: "var(--border-soft)",
      margin: "var(--sp-6) 0",
      ...style
    }
  }));
  return /*#__PURE__*/React.createElement("div", _extends({}, rest, {
    style: {
      display: "flex",
      alignItems: "center",
      gap: "var(--sp-4)",
      margin: "var(--sp-6) 0",
      ...style
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      flex: 1,
      height: 1,
      background: "var(--border-soft)"
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-smallcaps)",
      fontSize: "var(--text-micro)",
      letterSpacing: "var(--ls-label)",
      color: "var(--text-muted)"
    }
  }, label), /*#__PURE__*/React.createElement("span", {
    style: {
      flex: 1,
      height: 1,
      background: "var(--border-soft)"
    }
  }));
}
Object.assign(__ds_scope, { Divider });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Divider.jsx", error: String((e && e.message) || e) }); }

// components/core/Icon.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const CDN = "https://unpkg.com/lucide-static@0.469.0/icons/";

/** Monochrome glyph. Renders a Lucide outline icon as a masked box so it always
 *  takes the current text color. */
function Icon({
  name = "sparkles",
  size = 18,
  color = "currentColor",
  style,
  ...rest
}) {
  return /*#__PURE__*/React.createElement("span", _extends({
    "aria-hidden": "true"
  }, rest, {
    style: {
      display: "inline-block",
      width: size,
      height: size,
      flex: "0 0 auto",
      backgroundColor: color,
      WebkitMask: `url(${CDN}${name}.svg) center / contain no-repeat`,
      mask: `url(${CDN}${name}.svg) center / contain no-repeat`,
      ...style
    }
  }));
}
Object.assign(__ds_scope, { Icon });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Icon.jsx", error: String((e && e.message) || e) }); }

// components/chat/ChatMessage.jsx
try { (() => {
/** Three voices live in the log: the DM narrating, a player acting, and the
 *  system reporting mechanics. Each gets its own shape. */
const ROLES = {
  dm: {
    align: "flex-start",
    bubble: {
      background: "var(--surface-card)",
      border: "1px solid var(--border-soft)",
      backgroundImage: "var(--wash-lantern)"
    },
    glyph: "flame",
    glyphColor: "var(--lantern-400)"
  },
  player: {
    align: "flex-end",
    bubble: {
      background: "var(--surface-timber)",
      border: "1px solid var(--border-timber)"
    },
    glyph: "user",
    glyphColor: "var(--moss-300)"
  },
  system: {
    align: "center",
    bubble: {
      background: "transparent",
      border: "1px dashed var(--border-soft)"
    },
    glyph: "dices",
    glyphColor: "var(--text-muted)"
  }
};
function ChatMessage({
  role = "dm",
  author,
  time,
  children,
  avatar,
  style
}) {
  const r = ROLES[role] || ROLES.dm;
  const isSystem = role === "system";
  return /*#__PURE__*/React.createElement("article", {
    style: {
      display: "flex",
      flexDirection: "column",
      alignItems: r.align,
      gap: "6px",
      maxWidth: "100%",
      ...style
    }
  }, !isSystem && (author || time) ? /*#__PURE__*/React.createElement("span", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: "var(--sp-3)",
      fontFamily: "var(--font-smallcaps)",
      fontSize: "var(--text-micro)",
      letterSpacing: ".08em",
      color: "var(--text-muted)"
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: r.glyph,
    size: 12,
    color: r.glyphColor
  }), author, time ? /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--text-faint)",
      letterSpacing: 0,
      fontFamily: "var(--font-mono)"
    }
  }, time) : null) : null, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: "var(--sp-4)",
      maxWidth: isSystem ? "100%" : "min(640px, 88%)"
    }
  }, avatar && role === "dm" ? avatar : null, /*#__PURE__*/React.createElement("div", {
    style: {
      padding: isSystem ? "8px 16px" : "var(--sp-5) var(--sp-6)",
      borderRadius: role === "player" ? "var(--radius-organic-soft)" : "var(--radius-organic)",
      fontFamily: role === "dm" ? "var(--font-display)" : "var(--font-body)",
      fontSize: isSystem ? "var(--text-micro)" : role === "dm" ? "var(--text-lead)" : "var(--text-body)",
      lineHeight: role === "dm" ? 1.55 : "var(--lh-body)",
      color: isSystem ? "var(--text-muted)" : "var(--text-primary)",
      boxShadow: isSystem ? "none" : "var(--shadow-md)",
      ...r.bubble
    }
  }, children)));
}
Object.assign(__ds_scope, { ChatMessage });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/chat/ChatMessage.jsx", error: String((e && e.message) || e) }); }

// components/chat/DiceRoll.jsx
try { (() => {
function DiceRoll({
  notation = "1d20",
  total = 17,
  breakdown,
  outcome = "neutral",
  label,
  style
}) {
  const tone = outcome === "crit" ? "var(--moss-300)" : outcome === "fumble" ? "var(--ember-400)" : "var(--lantern-300)";
  const ring = outcome === "crit" ? "rgba(143,178,92,.4)" : outcome === "fumble" ? "rgba(194,84,58,.42)" : "rgba(232,169,74,.34)";
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: "var(--sp-5)",
      padding: "10px 18px 10px 14px",
      background: "var(--surface-inset)",
      border: `1px solid ${ring}`,
      borderRadius: "var(--radius-lg)",
      boxShadow: "inset 0 1px 2px rgba(0,0,0,.6)",
      ...style
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: "dices",
    size: 20,
    color: tone
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 2
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-mono)",
      fontSize: "var(--text-micro)",
      color: "var(--text-muted)",
      letterSpacing: "var(--ls-mono)"
    }
  }, label ? label + " · " : "", notation, breakdown ? " = " + breakdown : ""), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-display)",
      fontWeight: "var(--weight-black)",
      fontSize: "1.5rem",
      lineHeight: 1,
      color: tone
    }
  }, total)));
}
Object.assign(__ds_scope, { DiceRoll });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/chat/DiceRoll.jsx", error: String((e && e.message) || e) }); }

// components/core/Badge.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const TONES = {
  neutral: {
    color: "var(--text-secondary)",
    background: "rgba(243,236,222,.07)",
    border: "1px solid var(--border-soft)"
  },
  accent: {
    color: "var(--lantern-300)",
    background: "var(--accent-quiet)",
    border: "1px solid rgba(232,169,74,.34)"
  },
  moss: {
    color: "var(--moss-300)",
    background: "var(--accent-secondary-quiet)",
    border: "1px solid rgba(143,178,92,.34)"
  },
  danger: {
    color: "var(--ember-400)",
    background: "var(--danger-quiet)",
    border: "1px solid rgba(194,84,58,.36)"
  },
  magic: {
    color: "var(--fen-400)",
    background: "var(--info-quiet)",
    border: "1px solid rgba(95,169,163,.34)"
  }
};
function Badge({
  children,
  tone = "neutral",
  icon,
  style,
  ...rest
}) {
  return /*#__PURE__*/React.createElement("span", _extends({}, rest, {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: "6px",
      padding: "3px 10px",
      borderRadius: "var(--radius-pill)",
      fontFamily: "var(--font-smallcaps)",
      fontSize: "var(--text-micro)",
      letterSpacing: ".06em",
      lineHeight: 1.5,
      ...TONES[tone],
      ...style
    }
  }), icon ? /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: icon,
    size: 12
  }) : null, children);
}
Object.assign(__ds_scope, { Badge });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Badge.jsx", error: String((e && e.message) || e) }); }

// components/core/Button.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const HEIGHTS = {
  sm: "var(--control-h-sm)",
  md: "var(--control-h-md)",
  lg: "var(--control-h-lg)"
};
const PADS = {
  sm: "0 12px",
  md: "0 18px",
  lg: "0 26px"
};
const SIZES = {
  sm: "var(--text-micro)",
  md: "var(--text-small)",
  lg: "var(--text-body)"
};
const VARIANTS = {
  primary: {
    background: "linear-gradient(180deg, var(--lantern-400), var(--lantern-500))",
    color: "var(--text-on-accent)",
    border: "1px solid var(--lantern-600)",
    boxShadow: "var(--shadow-sm), var(--shadow-inset-top)"
  },
  secondary: {
    background: "var(--surface-timber)",
    color: "var(--text-primary)",
    border: "1px solid var(--border-timber)",
    boxShadow: "var(--shadow-inset-top)"
  },
  ghost: {
    background: "transparent",
    color: "var(--text-secondary)",
    border: "1px solid transparent"
  },
  outline: {
    background: "transparent",
    color: "var(--accent-secondary)",
    border: "1px solid var(--moss-600)"
  },
  danger: {
    background: "var(--danger-quiet)",
    color: "var(--ember-400)",
    border: "1px solid var(--ember-600)"
  }
};
const HOVER = {
  primary: {
    filter: "brightness(1.07)",
    boxShadow: "var(--shadow-sm), var(--glow-lantern)"
  },
  secondary: {
    background: "var(--bark-700)"
  },
  ghost: {
    background: "rgba(243,236,222,.06)",
    color: "var(--text-primary)"
  },
  outline: {
    background: "var(--accent-secondary-quiet)",
    color: "var(--moss-300)"
  },
  danger: {
    background: "rgba(194,84,58,.24)",
    color: "var(--ember-400)"
  }
};
function Button({
  children,
  variant = "primary",
  size = "md",
  icon,
  iconRight,
  fullWidth = false,
  disabled = false,
  loading = false,
  style,
  onClick,
  ...rest
}) {
  const [hover, setHover] = React.useState(false);
  const [press, setPress] = React.useState(false);
  return /*#__PURE__*/React.createElement("button", _extends({
    type: "button",
    disabled: disabled || loading,
    onClick: onClick,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => {
      setHover(false);
      setPress(false);
    },
    onMouseDown: () => setPress(true),
    onMouseUp: () => setPress(false)
  }, rest, {
    style: {
      display: fullWidth ? "flex" : "inline-flex",
      width: fullWidth ? "100%" : undefined,
      alignItems: "center",
      justifyContent: "center",
      gap: "var(--sp-3)",
      height: HEIGHTS[size],
      padding: PADS[size],
      fontSize: SIZES[size],
      fontFamily: "var(--font-body)",
      fontWeight: "var(--weight-medium)",
      letterSpacing: ".01em",
      borderRadius: "var(--radius-pill)",
      cursor: disabled ? "not-allowed" : "pointer",
      transition: "var(--transition-control)",
      whiteSpace: "nowrap",
      ...VARIANTS[variant],
      ...(hover && !disabled && !loading ? HOVER[variant] : null),
      transform: press && !disabled ? "translateY(1px) scale(.99)" : "none",
      opacity: disabled ? 0.42 : 1,
      ...style
    }
  }), loading ? /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: "loader",
    size: size === "lg" ? 18 : 15
  }) : icon ? /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: icon,
    size: size === "lg" ? 18 : 15
  }) : null, children, iconRight ? /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: iconRight,
    size: size === "lg" ? 18 : 15
  }) : null);
}
Object.assign(__ds_scope, { Button });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Button.jsx", error: String((e && e.message) || e) }); }

// components/core/IconButton.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const BOX = {
  sm: 30,
  md: 38,
  lg: 46
};
function IconButton({
  icon = "plus",
  label,
  size = "md",
  variant = "ghost",
  active = false,
  disabled = false,
  style,
  ...rest
}) {
  const [hover, setHover] = React.useState(false);
  const solid = variant === "solid";
  return /*#__PURE__*/React.createElement("button", _extends({
    type: "button",
    "aria-label": label,
    title: label,
    disabled: disabled,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false)
  }, rest, {
    style: {
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      width: BOX[size],
      height: BOX[size],
      borderRadius: "var(--radius-pill)",
      background: solid ? "var(--surface-timber)" : active || hover ? "rgba(243,236,222,.07)" : "transparent",
      border: solid ? "1px solid var(--border-timber)" : "1px solid transparent",
      color: active ? "var(--accent)" : hover ? "var(--text-primary)" : "var(--text-secondary)",
      cursor: disabled ? "not-allowed" : "pointer",
      opacity: disabled ? 0.4 : 1,
      transition: "var(--transition-control)",
      ...style
    }
  }), /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: icon,
    size: size === "sm" ? 15 : size === "lg" ? 20 : 17
  }));
}
Object.assign(__ds_scope, { IconButton });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/IconButton.jsx", error: String((e && e.message) || e) }); }

// components/chat/ChatComposer.jsx
try { (() => {
function ChatComposer({
  value = "",
  onChange,
  onSend,
  placeholder = "What do you do?",
  actions = ["dices", "backpack", "map"],
  disabled = false,
  style
}) {
  const [focus, setFocus] = React.useState(false);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: "var(--sp-4)",
      padding: "var(--sp-5)",
      background: "var(--surface-card)",
      backgroundImage: "var(--wash-lantern)",
      border: `1px solid ${focus ? "rgba(232,169,74,.4)" : "var(--border-soft)"}`,
      borderRadius: "var(--radius-xl)",
      boxShadow: focus ? "var(--shadow-lg), var(--glow-lantern)" : "var(--shadow-lg)",
      transition: "var(--transition-control)",
      ...style
    }
  }, /*#__PURE__*/React.createElement("textarea", {
    value: value,
    placeholder: placeholder,
    rows: 2,
    disabled: disabled,
    onChange: e => onChange && onChange(e.target.value),
    onFocus: () => setFocus(true),
    onBlur: () => setFocus(false),
    onKeyDown: e => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        onSend && onSend();
      }
    },
    style: {
      width: "100%",
      boxSizing: "border-box",
      resize: "none",
      border: "none",
      outline: "none",
      background: "transparent",
      color: "var(--text-primary)",
      fontFamily: "var(--font-body)",
      fontSize: "var(--text-body)",
      lineHeight: "var(--lh-body)",
      padding: "2px 4px"
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      gap: "var(--sp-4)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: "var(--sp-2)"
    }
  }, actions.map(a => /*#__PURE__*/React.createElement(__ds_scope.IconButton, {
    key: a,
    icon: a,
    label: a,
    size: "sm"
  }))), /*#__PURE__*/React.createElement(__ds_scope.Button, {
    size: "sm",
    iconRight: "send",
    onClick: onSend,
    disabled: disabled || !value.trim()
  }, "Send")));
}
Object.assign(__ds_scope, { ChatComposer });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/chat/ChatComposer.jsx", error: String((e && e.message) || e) }); }

// components/core/Dialog.jsx
try { (() => {
function Dialog({
  open = true,
  title,
  children,
  footer,
  onClose,
  width = 520
}) {
  if (!open) return null;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      inset: 0,
      display: "grid",
      placeItems: "center",
      background: "var(--scrim)",
      backdropFilter: "blur(6px)",
      zIndex: 40,
      padding: "var(--sp-8)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    role: "dialog",
    "aria-modal": "true",
    style: {
      width: "100%",
      maxWidth: width,
      background: "var(--surface-overlay)",
      backgroundImage: "var(--wash-lantern)",
      border: "1px solid var(--border-strong)",
      borderRadius: "var(--radius-xl)",
      boxShadow: "var(--shadow-overlay)",
      padding: "var(--sp-8)"
    }
  }, /*#__PURE__*/React.createElement("header", {
    style: {
      display: "flex",
      alignItems: "flex-start",
      justifyContent: "space-between",
      gap: "var(--sp-5)",
      marginBottom: "var(--sp-5)"
    }
  }, /*#__PURE__*/React.createElement("h2", {
    style: {
      font: "var(--weight-bold) var(--text-h2)/var(--lh-h2) var(--font-display)"
    }
  }, title), onClose ? /*#__PURE__*/React.createElement(__ds_scope.IconButton, {
    icon: "x",
    label: "Close",
    size: "sm",
    onClick: onClose
  }) : null), /*#__PURE__*/React.createElement("div", {
    style: {
      color: "var(--text-secondary)"
    }
  }, children), footer ? /*#__PURE__*/React.createElement("footer", {
    style: {
      display: "flex",
      justifyContent: "flex-end",
      gap: "var(--sp-4)",
      marginTop: "var(--sp-8)"
    }
  }, footer) : null));
}
Object.assign(__ds_scope, { Dialog });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Dialog.jsx", error: String((e && e.message) || e) }); }

// components/core/Tag.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function Tag({
  children,
  onRemove,
  selected = false,
  onClick,
  style,
  ...rest
}) {
  const [hover, setHover] = React.useState(false);
  return /*#__PURE__*/React.createElement("span", _extends({
    onClick: onClick,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false)
  }, rest, {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: "var(--sp-3)",
      padding: "5px 12px",
      borderRadius: "var(--radius-pill)",
      fontSize: "var(--text-small)",
      background: selected ? "var(--accent-quiet)" : hover && onClick ? "rgba(243,236,222,.07)" : "var(--surface-raised)",
      color: selected ? "var(--lantern-300)" : "var(--text-secondary)",
      border: `1px solid ${selected ? "rgba(232,169,74,.4)" : "var(--border-soft)"}`,
      cursor: onClick ? "pointer" : "default",
      transition: "var(--transition-control)",
      ...style
    }
  }), children, onRemove ? /*#__PURE__*/React.createElement("span", {
    onClick: e => {
      e.stopPropagation();
      onRemove();
    },
    style: {
      display: "inline-flex",
      cursor: "pointer",
      opacity: .7
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: "x",
    size: 12
  })) : null);
}
Object.assign(__ds_scope, { Tag });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Tag.jsx", error: String((e && e.message) || e) }); }

// components/forms/Checkbox.jsx
try { (() => {
function Checkbox({
  checked = false,
  onChange,
  label,
  disabled = false,
  style
}) {
  return /*#__PURE__*/React.createElement("label", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: "var(--sp-4)",
      cursor: disabled ? "not-allowed" : "pointer",
      opacity: disabled ? .5 : 1,
      ...style
    }
  }, /*#__PURE__*/React.createElement("span", {
    onClick: () => !disabled && onChange && onChange(!checked),
    style: {
      display: "inline-grid",
      placeItems: "center",
      width: 20,
      height: 20,
      borderRadius: "7px",
      background: checked ? "var(--moss-500)" : "var(--surface-inset)",
      border: `1px solid ${checked ? "var(--moss-600)" : "var(--border-soft)"}`,
      boxShadow: checked ? "var(--glow-moss)" : "inset 0 1px 2px rgba(0,0,0,.5)",
      transition: "var(--transition-control)"
    }
  }, checked ? /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: "check",
    size: 13,
    color: "var(--loam-950)"
  }) : null), label ? /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-small)",
      color: "var(--text-secondary)"
    }
  }, label) : null);
}
Object.assign(__ds_scope, { Checkbox });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Checkbox.jsx", error: String((e && e.message) || e) }); }

// components/forms/Field.jsx
try { (() => {
function Field({
  label,
  hint,
  error,
  children,
  htmlFor
}) {
  return /*#__PURE__*/React.createElement("label", {
    htmlFor: htmlFor,
    style: {
      display: "grid",
      gap: "var(--sp-3)"
    }
  }, label ? /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-smallcaps)",
      fontSize: "var(--text-micro)",
      letterSpacing: "var(--ls-label)",
      color: "var(--text-muted)"
    }
  }, label) : null, children, error ? /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-micro)",
      color: "var(--ember-400)"
    }
  }, error) : hint ? /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-micro)",
      color: "var(--text-faint)"
    }
  }, hint) : null);
}
Object.assign(__ds_scope, { Field });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Field.jsx", error: String((e && e.message) || e) }); }

// components/forms/Input.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function Input({
  value,
  onChange,
  placeholder,
  icon,
  type = "text",
  invalid = false,
  disabled = false,
  style,
  ...rest
}) {
  const [focus, setFocus] = React.useState(false);
  const box = {
    width: "100%",
    boxSizing: "border-box",
    height: "var(--control-h-md)",
    padding: "0 14px",
    borderRadius: "var(--radius-md)",
    background: "var(--surface-inset)",
    color: "var(--text-primary)",
    fontFamily: "var(--font-body)",
    fontSize: "var(--text-body)",
    border: `1px solid ${invalid ? "var(--ember-600)" : focus ? "var(--lantern-500)" : "var(--border-soft)"}`,
    boxShadow: focus ? "0 0 0 3px rgba(232,169,74,.16)" : "inset 0 1px 2px rgba(0,0,0,.5)",
    outline: "none",
    transition: "var(--transition-control)",
    opacity: disabled ? .5 : 1
  };
  const input = /*#__PURE__*/React.createElement("input", _extends({
    type: type,
    value: value,
    placeholder: placeholder,
    disabled: disabled,
    onChange: e => onChange && onChange(e.target.value),
    onFocus: () => setFocus(true),
    onBlur: () => setFocus(false)
  }, rest, {
    style: {
      ...box,
      paddingLeft: icon ? 38 : 14,
      ...style
    }
  }));
  if (!icon) return input;
  return /*#__PURE__*/React.createElement("span", {
    style: {
      position: "relative",
      display: "block"
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: icon,
    size: 16,
    style: {
      position: "absolute",
      left: 13,
      top: "50%",
      transform: "translateY(-50%)",
      backgroundColor: "var(--text-muted)"
    }
  }), input);
}
Object.assign(__ds_scope, { Input });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Input.jsx", error: String((e && e.message) || e) }); }

// components/forms/Select.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function Select({
  value,
  onChange,
  options = [],
  disabled = false,
  invalid = false,
  style,
  ...rest
}) {
  const [focus, setFocus] = React.useState(false);
  const box = {
    width: "100%",
    boxSizing: "border-box",
    height: "var(--control-h-md)",
    padding: "0 14px",
    borderRadius: "var(--radius-md)",
    background: "var(--surface-inset)",
    color: "var(--text-primary)",
    fontFamily: "var(--font-body)",
    fontSize: "var(--text-body)",
    border: `1px solid ${invalid ? "var(--ember-600)" : focus ? "var(--lantern-500)" : "var(--border-soft)"}`,
    boxShadow: focus ? "0 0 0 3px rgba(232,169,74,.16)" : "inset 0 1px 2px rgba(0,0,0,.5)",
    outline: "none",
    transition: "var(--transition-control)",
    opacity: disabled ? .5 : 1
  };
  return /*#__PURE__*/React.createElement("span", {
    style: {
      position: "relative",
      display: "block"
    }
  }, /*#__PURE__*/React.createElement("select", _extends({
    value: value,
    disabled: disabled,
    onChange: e => onChange && onChange(e.target.value),
    onFocus: () => setFocus(true),
    onBlur: () => setFocus(false)
  }, rest, {
    style: {
      ...box,
      appearance: "none",
      paddingRight: 38,
      cursor: "pointer",
      ...style
    }
  }), options.map(o => {
    const opt = typeof o === "string" ? {
      value: o,
      label: o
    } : o;
    return /*#__PURE__*/React.createElement("option", {
      key: opt.value,
      value: opt.value
    }, opt.label);
  })), /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: "chevron-down",
    size: 16,
    style: {
      position: "absolute",
      right: 13,
      top: "50%",
      transform: "translateY(-50%)",
      backgroundColor: "var(--text-muted)",
      pointerEvents: "none"
    }
  }));
}
Object.assign(__ds_scope, { Select });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Select.jsx", error: String((e && e.message) || e) }); }

// components/forms/Switch.jsx
try { (() => {
function Switch({
  checked = false,
  onChange,
  label,
  disabled = false,
  style
}) {
  return /*#__PURE__*/React.createElement("label", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: "var(--sp-4)",
      cursor: disabled ? "not-allowed" : "pointer",
      opacity: disabled ? .5 : 1,
      ...style
    }
  }, /*#__PURE__*/React.createElement("span", {
    onClick: () => !disabled && onChange && onChange(!checked),
    style: {
      position: "relative",
      width: 42,
      height: 24,
      borderRadius: "var(--radius-pill)",
      background: checked ? "var(--lantern-500)" : "var(--loam-700)",
      border: `1px solid ${checked ? "var(--lantern-600)" : "var(--border-soft)"}`,
      boxShadow: checked ? "var(--glow-lantern)" : "inset 0 1px 3px rgba(0,0,0,.55)",
      transition: "var(--transition-control)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      position: "absolute",
      top: 2,
      left: checked ? 20 : 2,
      width: 18,
      height: 18,
      borderRadius: "50%",
      background: checked ? "var(--parchment-100)" : "var(--parchment-400)",
      transition: "left var(--dur-base) var(--ease-out-soft)"
    }
  })), label ? /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-small)",
      color: "var(--text-secondary)"
    }
  }, label) : null);
}
Object.assign(__ds_scope, { Switch });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Switch.jsx", error: String((e && e.message) || e) }); }

// components/forms/Textarea.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function Textarea({
  value,
  onChange,
  placeholder,
  rows = 3,
  invalid = false,
  disabled = false,
  style,
  ...rest
}) {
  const [focus, setFocus] = React.useState(false);
  const box = {
    width: "100%",
    boxSizing: "border-box",
    height: "var(--control-h-md)",
    padding: "0 14px",
    borderRadius: "var(--radius-md)",
    background: "var(--surface-inset)",
    color: "var(--text-primary)",
    fontFamily: "var(--font-body)",
    fontSize: "var(--text-body)",
    border: `1px solid ${invalid ? "var(--ember-600)" : focus ? "var(--lantern-500)" : "var(--border-soft)"}`,
    boxShadow: focus ? "0 0 0 3px rgba(232,169,74,.16)" : "inset 0 1px 2px rgba(0,0,0,.5)",
    outline: "none",
    transition: "var(--transition-control)",
    opacity: disabled ? .5 : 1
  };
  return /*#__PURE__*/React.createElement("textarea", _extends({
    rows: rows,
    value: value,
    placeholder: placeholder,
    disabled: disabled,
    onChange: e => onChange && onChange(e.target.value),
    onFocus: () => setFocus(true),
    onBlur: () => setFocus(false)
  }, rest, {
    style: {
      ...box,
      height: "auto",
      padding: "10px 14px",
      lineHeight: "var(--lh-body)",
      resize: "vertical",
      ...style
    }
  }));
}
Object.assign(__ds_scope, { Textarea });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Textarea.jsx", error: String((e && e.message) || e) }); }

// components/game/AbilityScore.jsx
try { (() => {
function AbilityScore({
  abbr = "STR",
  score = 14,
  modifier,
  compact = false,
  style
}) {
  const mod = modifier != null ? modifier : Math.floor((score - 10) / 2);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      justifyItems: "center",
      gap: compact ? 0 : 2,
      padding: compact ? "6px 8px" : "8px 6px 10px",
      minWidth: compact ? 48 : 58,
      background: "var(--surface-inset)",
      border: "1px solid var(--border-hairline)",
      borderRadius: "var(--radius-md)",
      ...style
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-smallcaps)",
      fontSize: "var(--text-micro)",
      letterSpacing: ".1em",
      color: "var(--text-faint)"
    }
  }, abbr), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-display)",
      fontWeight: "var(--weight-bold)",
      fontSize: compact ? "1.05rem" : "1.25rem",
      lineHeight: 1.1,
      color: "var(--text-primary)"
    }
  }, score), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-mono)",
      fontSize: "var(--text-micro)",
      color: mod >= 0 ? "var(--moss-300)" : "var(--ember-400)"
    }
  }, mod >= 0 ? "+" + mod : mod));
}
Object.assign(__ds_scope, { AbilityScore });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/game/AbilityScore.jsx", error: String((e && e.message) || e) }); }

// components/game/ResourceBar.jsx
try { (() => {
const TONES = {
  hp: ["var(--hp-full)", "var(--hp-low)", "var(--hp-crit)"],
  xp: ["var(--xp-fill)"],
  spell: ["var(--fen-400)"]
};
function ResourceBar({
  label = "HP",
  value = 24,
  max = 32,
  kind = "hp",
  suffix,
  style
}) {
  const pct = Math.max(0, Math.min(1, max ? value / max : 0));
  const ramp = TONES[kind] || TONES.xp;
  const fill = kind === "hp" ? pct > 0.5 ? ramp[0] : pct > 0.25 ? ramp[1] : ramp[2] : ramp[0];
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gap: 5,
      ...style
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      justifyContent: "space-between",
      alignItems: "baseline",
      gap: "var(--sp-4)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-smallcaps)",
      fontSize: "var(--text-micro)",
      letterSpacing: "var(--ls-label)",
      color: "var(--text-muted)"
    }
  }, label), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-mono)",
      fontSize: "var(--text-micro)",
      color: "var(--text-secondary)"
    }
  }, value, "/", max, suffix ? " " + suffix : "")), /*#__PURE__*/React.createElement("div", {
    style: {
      height: 8,
      borderRadius: "var(--radius-pill)",
      background: "var(--surface-inset)",
      boxShadow: "inset 0 1px 2px rgba(0,0,0,.6)",
      overflow: "hidden"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: (pct * 100).toFixed(1) + "%",
      height: "100%",
      borderRadius: "var(--radius-pill)",
      background: fill,
      transition: "width var(--dur-slow) var(--ease-out-soft), background-color var(--dur-base) var(--ease-standard)"
    }
  })));
}
Object.assign(__ds_scope, { ResourceBar });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/game/ResourceBar.jsx", error: String((e && e.message) || e) }); }

// components/game/PlayerStatCard.jsx
try { (() => {
function PlayerStatCard({
  name = "Brakka Nine-Fingers",
  subtitle = "Goblin Rogue · Level 4",
  portrait,
  hp = {
    value: 24,
    max: 32
  },
  ac = 15,
  initiative = 3,
  conditions = [],
  abilities = [],
  active = false,
  compact = false,
  onClick,
  style
}) {
  return /*#__PURE__*/React.createElement(__ds_scope.Card, {
    tone: "raised",
    lantern: active,
    onClick: onClick,
    padding: "var(--sp-5)",
    style: {
      border: active ? "1px solid rgba(232,169,74,.45)" : "1px solid var(--border-soft)",
      boxShadow: active ? "var(--shadow-md), var(--glow-lantern)" : "var(--shadow-md)",
      cursor: onClick ? "pointer" : "default",
      transition: "var(--transition-control)",
      ...style
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: "var(--sp-4)",
      alignItems: "center",
      marginBottom: "var(--sp-4)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 46,
      height: 46,
      flex: "0 0 auto",
      borderRadius: "var(--radius-organic-soft)",
      background: portrait ? `center/cover url(${portrait})` : "linear-gradient(160deg, var(--bark-600), var(--loam-700))",
      border: "1px solid var(--border-timber)",
      display: "grid",
      placeItems: "center"
    }
  }, portrait ? null : /*#__PURE__*/React.createElement(__ds_scope.Icon, {
    name: "user",
    size: 20,
    color: "var(--parchment-400)"
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      font: "var(--weight-bold) 1.0625rem/1.25 var(--font-display)",
      color: "var(--text-primary)",
      whiteSpace: "nowrap",
      overflow: "hidden",
      textOverflow: "ellipsis"
    }
  }, name), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: "var(--text-micro)",
      color: "var(--text-muted)"
    }
  }, subtitle))), /*#__PURE__*/React.createElement(__ds_scope.ResourceBar, {
    label: "HP",
    value: hp.value,
    max: hp.max,
    kind: "hp"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: "var(--sp-3)",
      margin: "var(--sp-4) 0 0"
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.Badge, {
    icon: "shield"
  }, "AC ", ac), /*#__PURE__*/React.createElement(__ds_scope.Badge, {
    icon: "footprints"
  }, "Init +", initiative)), conditions.length ? /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexWrap: "wrap",
      gap: "var(--sp-3)",
      marginTop: "var(--sp-3)"
    }
  }, conditions.map(c => /*#__PURE__*/React.createElement(__ds_scope.Badge, {
    key: c,
    tone: "danger"
  }, c))) : null, abilities.length && !compact ? /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(6, 1fr)",
      gap: "var(--sp-2)",
      marginTop: "var(--sp-5)"
    }
  }, abilities.map(a => /*#__PURE__*/React.createElement(__ds_scope.AbilityScore, {
    key: a.abbr,
    abbr: a.abbr,
    score: a.score,
    compact: true
  }))) : null);
}
Object.assign(__ds_scope, { PlayerStatCard });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/game/PlayerStatCard.jsx", error: String((e && e.message) || e) }); }

// components/game/SceneImage.jsx
try { (() => {
function SceneImage({
  src,
  caption,
  chapter,
  height = 220,
  children,
  style
}) {
  return /*#__PURE__*/React.createElement("figure", {
    style: {
      position: "relative",
      margin: 0,
      height,
      borderRadius: "var(--radius-organic)",
      overflow: "hidden",
      border: "1px solid var(--border-soft)",
      boxShadow: "var(--shadow-md)",
      background: src ? `center/cover no-repeat url(${src})` : "linear-gradient(155deg, var(--loam-700), var(--bark-900) 60%, var(--loam-900))",
      ...style
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      inset: 0,
      backgroundImage: "var(--grain)",
      pointerEvents: "none"
    }
  }), !src ? /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      inset: 0,
      display: "grid",
      placeItems: "center",
      textAlign: "center",
      padding: "var(--sp-6)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-smallcaps)",
      fontSize: "var(--text-micro)",
      letterSpacing: "var(--ls-label)",
      color: "var(--text-faint)"
    }
  }, children || "Scene art goes here")) : null, /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      inset: 0,
      background: "var(--scrim-bottom)"
    }
  }), /*#__PURE__*/React.createElement("figcaption", {
    style: {
      position: "absolute",
      left: "var(--sp-6)",
      right: "var(--sp-6)",
      bottom: "var(--sp-5)",
      display: "grid",
      gap: "var(--sp-3)",
      justifyItems: "start"
    }
  }, chapter ? /*#__PURE__*/React.createElement(__ds_scope.Badge, {
    tone: "accent"
  }, chapter) : null, caption ? /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-display)",
      fontSize: "var(--text-h3)",
      lineHeight: 1.25,
      color: "var(--text-primary)",
      textShadow: "0 2px 12px rgba(0,0,0,.8)"
    }
  }, caption) : null));
}
Object.assign(__ds_scope, { SceneImage });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/game/SceneImage.jsx", error: String((e && e.message) || e) }); }

// mui/goblinPubTheme.js
try { (() => {
/**
 * Goblin Pub — MUI theme options.
 *
 * Plain data, no imports, so it can be dropped into any React app:
 *
 *   import { createTheme, ThemeProvider, CssBaseline } from "@mui/material";
 *   import { goblinPubThemeOptions } from "./goblinPubTheme";
 *   const theme = createTheme(goblinPubThemeOptions);
 *
 * Link the design system's styles.css alongside it if you also want the raw
 * CSS custom properties (--surface-card, --radius-organic, …) available to
 * hand-written CSS. The values below are the same tokens, resolved to literals
 * because MUI needs real colours for its own contrast + alpha maths.
 */

const goblinPubTokens = {
  loam: {
    950: "#0B0E09",
    900: "#12160F",
    850: "#171C13",
    800: "#1E2418",
    700: "#283022",
    600: "#36402C",
    500: "#4A5539",
    400: "#5F6B4A"
  },
  bark: {
    900: "#241A11",
    800: "#33261A",
    700: "#463320",
    600: "#5C4429",
    500: "#7A5C36",
    400: "#9A7749"
  },
  moss: {
    700: "#3F5A28",
    600: "#527334",
    500: "#6E9142",
    400: "#8FB25C",
    300: "#B4D083",
    200: "#D3E5B0"
  },
  lantern: {
    700: "#8A5410",
    600: "#B0731C",
    500: "#D08C2A",
    400: "#E8A94A",
    300: "#F3C87C",
    200: "#F9E0B4"
  },
  ember: {
    600: "#9C3B26",
    500: "#C2543A",
    400: "#DC7458"
  },
  fen: {
    600: "#2E6360",
    500: "#3E8480",
    400: "#5FA9A3"
  },
  parchment: {
    100: "#F2ECDE",
    200: "#E3DACA",
    300: "#C6BCA6",
    400: "#9E947F",
    500: "#7B7263"
  },
  radius: {
    xs: 6,
    sm: 10,
    md: 14,
    lg: 20,
    xl: 28,
    pill: 999,
    organic: "22px 16px 24px 18px",
    organicSoft: "18px 22px 16px 20px"
  },
  shadow: {
    insetTop: "inset 0 1px 0 rgba(243,236,222,.06)",
    sm: "0 1px 2px rgba(0,0,0,.5)",
    md: "0 6px 18px -6px rgba(0,0,0,.62), inset 0 1px 0 rgba(243,236,222,.06)",
    lg: "0 20px 44px -18px rgba(0,0,0,.78), inset 0 1px 0 rgba(243,236,222,.06)",
    overlay: "0 32px 80px -24px rgba(0,0,0,.85)",
    glowLantern: "0 0 28px -6px rgba(232,169,74,.34)",
    glowMoss: "0 0 24px -8px rgba(143,178,92,.3)"
  },
  wash: {
    lantern: "radial-gradient(120% 80% at 50% -20%, rgba(232,169,74,.10), transparent 62%)",
    moss: "radial-gradient(100% 70% at 0% 0%, rgba(110,145,66,.12), transparent 60%)",
    scrimBottom: "linear-gradient(to top, rgba(11,14,9,.92) 8%, rgba(11,14,9,0) 92%)",
    grain: "repeating-linear-gradient(122deg, rgba(243,236,222,.014) 0 2px, transparent 2px 4px)"
  },
  border: {
    hairline: "rgba(226,214,186,.08)",
    soft: "rgba(226,214,186,.14)",
    strong: "rgba(226,214,186,.24)",
    timber: "#463320"
  },
  font: {
    display: '"Alegreya", Georgia, "Times New Roman", serif',
    smallcaps: '"Alegreya SC", "Alegreya", Georgia, serif',
    body: '"Alegreya Sans", "Avenir Next", system-ui, sans-serif',
    mono: '"JetBrains Mono", ui-monospace, Menlo, monospace'
  },
  ease: {
    standard: "cubic-bezier(.32,.72,.32,1)",
    outSoft: "cubic-bezier(.16,.84,.44,1)",
    in: "cubic-bezier(.55,.06,.68,.19)"
  }
};
const t = goblinPubTokens;
const goblinPubThemeOptions = {
  /* The app is dark-only. There is no light mode and there should not be one. */
  palette: {
    mode: "dark",
    common: {
      black: t.loam[950],
      white: t.parchment[100]
    },
    primary: {
      main: t.lantern[400],
      light: t.lantern[300],
      dark: t.lantern[500],
      contrastText: t.loam[950]
    },
    secondary: {
      main: t.moss[400],
      light: t.moss[300],
      dark: t.moss[500],
      contrastText: t.loam[950]
    },
    error: {
      main: t.ember[500],
      light: t.ember[400],
      dark: t.ember[600],
      contrastText: t.parchment[100]
    },
    warning: {
      main: t.lantern[400],
      light: t.lantern[300],
      dark: t.lantern[500],
      contrastText: t.loam[950]
    },
    info: {
      main: t.fen[400],
      light: "#7FC0BA",
      dark: t.fen[600],
      contrastText: t.loam[950]
    },
    success: {
      main: t.moss[400],
      light: t.moss[300],
      dark: t.moss[600],
      contrastText: t.loam[950]
    },
    background: {
      default: t.loam[950],
      paper: t.loam[850]
    },
    text: {
      primary: t.parchment[100],
      secondary: t.parchment[300],
      disabled: t.parchment[500]
    },
    divider: t.border.soft,
    action: {
      active: t.parchment[200],
      hover: "rgba(243,236,222,.06)",
      hoverOpacity: 0.06,
      selected: "rgba(232,169,74,.14)",
      selectedOpacity: 0.14,
      disabled: "rgba(243,236,222,.3)",
      disabledBackground: "rgba(243,236,222,.08)",
      focus: "rgba(232,169,74,.16)"
    },
    /* Extra ramps, reachable as theme.palette.goblin.* */
    goblin: t
  },
  shape: {
    borderRadius: t.radius.md
  },
  spacing: 4,
  // theme.spacing(2) = 8px, (4) = 16px, matching --sp-3 / --sp-5

  typography: {
    fontFamily: t.font.body,
    fontSize: 16,
    htmlFontSize: 16,
    h1: {
      fontFamily: t.font.display,
      fontWeight: 700,
      fontSize: "2.75rem",
      lineHeight: 1.06,
      letterSpacing: "-0.015em"
    },
    h2: {
      fontFamily: t.font.display,
      fontWeight: 700,
      fontSize: "2rem",
      lineHeight: 1.14,
      letterSpacing: "-0.01em"
    },
    h3: {
      fontFamily: t.font.display,
      fontWeight: 700,
      fontSize: "1.5rem",
      lineHeight: 1.2
    },
    h4: {
      fontFamily: t.font.display,
      fontWeight: 700,
      fontSize: "1.1875rem",
      lineHeight: 1.3
    },
    h5: {
      fontFamily: t.font.display,
      fontWeight: 700,
      fontSize: "1.0625rem",
      lineHeight: 1.25
    },
    h6: {
      fontFamily: t.font.smallcaps,
      fontWeight: 500,
      fontSize: "0.9375rem",
      lineHeight: 1.3,
      letterSpacing: "0.04em"
    },
    subtitle1: {
      fontFamily: t.font.body,
      fontSize: "1.125rem",
      lineHeight: 1.6
    },
    subtitle2: {
      fontFamily: t.font.smallcaps,
      fontSize: "0.78125rem",
      lineHeight: 1.4,
      letterSpacing: "0.14em",
      textTransform: "uppercase"
    },
    body1: {
      fontFamily: t.font.body,
      fontSize: "1rem",
      lineHeight: 1.6
    },
    body2: {
      fontFamily: t.font.body,
      fontSize: "0.875rem",
      lineHeight: 1.5
    },
    button: {
      fontFamily: t.font.body,
      fontWeight: 500,
      fontSize: "0.875rem",
      letterSpacing: "0.01em",
      textTransform: "none"
    },
    caption: {
      fontFamily: t.font.mono,
      fontSize: "0.78125rem",
      lineHeight: 1.4,
      letterSpacing: "0.02em"
    },
    overline: {
      fontFamily: t.font.smallcaps,
      fontSize: "0.78125rem",
      letterSpacing: "0.14em",
      textTransform: "uppercase",
      lineHeight: 1.4
    }
  },
  /* MUI wants 25 entries. Ours are warm and deep rather than neutral. */
  shadows: ["none", t.shadow.sm, t.shadow.sm, t.shadow.md, t.shadow.md, t.shadow.md, t.shadow.md, t.shadow.md, t.shadow.lg, t.shadow.lg, t.shadow.lg, t.shadow.lg, t.shadow.lg, t.shadow.lg, t.shadow.lg, t.shadow.lg, t.shadow.overlay, t.shadow.overlay, t.shadow.overlay, t.shadow.overlay, t.shadow.overlay, t.shadow.overlay, t.shadow.overlay, t.shadow.overlay, t.shadow.overlay],
  transitions: {
    duration: {
      shortest: 90,
      shorter: 150,
      short: 150,
      standard: 220,
      complex: 400,
      enteringScreen: 220,
      leavingScreen: 150
    },
    easing: {
      easeInOut: t.ease.standard,
      easeOut: t.ease.outSoft,
      easeIn: t.ease.in,
      sharp: t.ease.standard
    }
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          backgroundColor: t.loam[950],
          color: t.parchment[100],
          fontFamily: t.font.body,
          textWrap: "pretty",
          "::selection": {
            background: "rgba(232,169,74,.28)"
          }
        },
        a: {
          color: t.lantern[300],
          textUnderlineOffset: 3,
          textDecorationColor: "rgba(243,200,124,.4)"
        },
        "a:hover": {
          color: t.lantern[200],
          textDecorationColor: "currentColor"
        }
      }
    },
    MuiButton: {
      defaultProps: {
        disableElevation: true,
        variant: "contained"
      },
      styleOverrides: {
        root: {
          borderRadius: t.radius.pill,
          paddingInline: 18,
          minHeight: 40,
          transition: `background-color 150ms ${t.ease.standard}, box-shadow 150ms ${t.ease.standard}, filter 150ms ${t.ease.standard}, transform 90ms ${t.ease.standard}`,
          "&:active": {
            transform: "translateY(1px) scale(.99)"
          },
          "&.Mui-disabled": {
            opacity: 0.42
          }
        },
        sizeSmall: {
          minHeight: 32,
          paddingInline: 12,
          fontSize: "0.78125rem"
        },
        sizeLarge: {
          minHeight: 48,
          paddingInline: 26,
          fontSize: "1rem"
        },
        containedPrimary: {
          background: `linear-gradient(180deg, ${t.lantern[400]}, ${t.lantern[500]})`,
          border: `1px solid ${t.lantern[600]}`,
          color: t.loam[950],
          boxShadow: `${t.shadow.sm}, ${t.shadow.insetTop}`,
          "&:hover": {
            filter: "brightness(1.07)",
            boxShadow: `${t.shadow.sm}, ${t.shadow.glowLantern}`
          }
        },
        containedSecondary: {
          background: t.bark[800],
          border: `1px solid ${t.border.timber}`,
          color: t.parchment[100],
          boxShadow: t.shadow.insetTop,
          "&:hover": {
            background: t.bark[700]
          }
        },
        outlined: {
          borderColor: t.moss[600],
          color: t.moss[400],
          "&:hover": {
            background: "rgba(143,178,92,.14)",
            borderColor: t.moss[500],
            color: t.moss[300]
          }
        },
        text: {
          color: t.parchment[300],
          "&:hover": {
            background: "rgba(243,236,222,.06)",
            color: t.parchment[100]
          }
        }
      }
    },
    MuiIconButton: {
      styleOverrides: {
        root: {
          borderRadius: t.radius.pill,
          color: t.parchment[300],
          transition: `background-color 150ms ${t.ease.standard}, color 150ms ${t.ease.standard}`,
          "&:hover": {
            background: "rgba(243,236,222,.07)",
            color: t.parchment[100]
          }
        },
        colorPrimary: {
          color: t.lantern[400]
        }
      }
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: "none",
          backgroundColor: t.loam[850],
          border: `1px solid ${t.border.soft}`
        },
        rounded: {
          borderRadius: t.radius.lg
        },
        outlined: {
          borderColor: t.border.soft
        },
        elevation0: {
          border: "none"
        }
      }
    },
    MuiCard: {
      defaultProps: {
        elevation: 3
      },
      styleOverrides: {
        root: {
          /* The house look: an uneven, hand-cut radius. Use borderRadius: 20
             on a card that must tile flush with others. */
          borderRadius: t.radius.organic,
          backgroundColor: t.loam[800],
          border: `1px solid ${t.border.soft}`,
          boxShadow: t.shadow.md
        }
      }
    },
    MuiCardContent: {
      styleOverrides: {
        root: {
          padding: 20,
          "&:last-child": {
            paddingBottom: 20
          }
        }
      }
    },
    MuiCardHeader: {
      styleOverrides: {
        root: {
          padding: "20px 20px 0"
        },
        title: {
          fontFamily: t.font.display,
          fontWeight: 700,
          fontSize: "1.1875rem",
          lineHeight: 1.3
        },
        subheader: {
          fontSize: "0.78125rem",
          color: t.parchment[400]
        }
      }
    },
    MuiChip: {
      styleOverrides: {
        root: {
          borderRadius: t.radius.pill,
          backgroundColor: t.loam[800],
          border: `1px solid ${t.border.soft}`,
          color: t.parchment[300],
          fontSize: "0.875rem"
        },
        label: {
          paddingInline: 12
        },
        filledPrimary: {
          background: "rgba(232,169,74,.14)",
          border: "1px solid rgba(232,169,74,.34)",
          color: t.lantern[300]
        },
        filledSecondary: {
          background: "rgba(143,178,92,.14)",
          border: "1px solid rgba(143,178,92,.34)",
          color: t.moss[300]
        },
        deleteIcon: {
          color: "inherit",
          opacity: 0.7,
          "&:hover": {
            color: "inherit",
            opacity: 1
          }
        }
      }
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          borderRadius: t.radius.md,
          backgroundColor: "#0E120C",
          boxShadow: "inset 0 1px 2px rgba(0,0,0,.5)",
          transition: `box-shadow 150ms ${t.ease.standard}`,
          "& .MuiOutlinedInput-notchedOutline": {
            borderColor: t.border.soft
          },
          "&:hover .MuiOutlinedInput-notchedOutline": {
            borderColor: t.border.strong
          },
          "&.Mui-focused": {
            boxShadow: "0 0 0 3px rgba(232,169,74,.16)"
          },
          "&.Mui-focused .MuiOutlinedInput-notchedOutline": {
            borderColor: t.lantern[500],
            borderWidth: 1
          },
          "&.Mui-error .MuiOutlinedInput-notchedOutline": {
            borderColor: t.ember[600]
          }
        },
        input: {
          padding: "10px 14px",
          "&::placeholder": {
            color: t.parchment[500],
            opacity: 1
          }
        }
      }
    },
    MuiInputLabel: {
      styleOverrides: {
        root: {
          fontFamily: t.font.smallcaps,
          fontSize: "0.78125rem",
          letterSpacing: "0.14em",
          textTransform: "uppercase",
          color: t.parchment[400],
          "&.Mui-focused": {
            color: t.lantern[300]
          }
        }
      }
    },
    MuiFormHelperText: {
      styleOverrides: {
        root: {
          fontSize: "0.78125rem",
          color: t.parchment[500],
          marginLeft: 2
        }
      }
    },
    MuiTextField: {
      defaultProps: {
        variant: "outlined",
        size: "small"
      }
    },
    MuiCheckbox: {
      styleOverrides: {
        root: {
          color: t.parchment[400],
          borderRadius: 7,
          "&.Mui-checked": {
            color: t.moss[500]
          }
        }
      }
    },
    MuiRadio: {
      styleOverrides: {
        root: {
          color: t.parchment[400],
          "&.Mui-checked": {
            color: t.moss[500]
          }
        }
      }
    },
    MuiSwitch: {
      styleOverrides: {
        switchBase: {
          "&.Mui-checked": {
            color: t.parchment[100]
          },
          "&.Mui-checked + .MuiSwitch-track": {
            backgroundColor: t.lantern[500],
            opacity: 1
          }
        },
        track: {
          backgroundColor: t.loam[700],
          opacity: 1,
          borderRadius: t.radius.pill
        },
        thumb: {
          backgroundColor: t.parchment[400]
        }
      }
    },
    MuiSlider: {
      styleOverrides: {
        rail: {
          backgroundColor: t.loam[700],
          opacity: 1
        },
        track: {
          backgroundColor: t.lantern[400],
          border: "none"
        },
        thumb: {
          backgroundColor: t.parchment[100],
          "&:hover, &.Mui-focusVisible": {
            boxShadow: t.shadow.glowLantern
          }
        }
      }
    },
    MuiLinearProgress: {
      styleOverrides: {
        root: {
          height: 8,
          borderRadius: t.radius.pill,
          backgroundColor: "#0E120C"
        },
        bar: {
          borderRadius: t.radius.pill,
          backgroundColor: t.moss[400]
        }
      }
    },
    MuiDialog: {
      styleOverrides: {
        paper: {
          borderRadius: t.radius.xl,
          backgroundColor: "#151A11",
          backgroundImage: t.wash.lantern,
          border: `1px solid ${t.border.strong}`,
          boxShadow: t.shadow.overlay
        }
      }
    },
    MuiBackdrop: {
      styleOverrides: {
        root: {
          backgroundColor: "rgba(8,10,7,.72)",
          backdropFilter: "blur(6px)"
        }
      }
    },
    MuiDialogTitle: {
      styleOverrides: {
        root: {
          fontFamily: t.font.display,
          fontWeight: 700,
          fontSize: "1.5rem",
          padding: "32px 32px 16px"
        }
      }
    },
    MuiDialogContent: {
      styleOverrides: {
        root: {
          padding: "0 32px",
          color: t.parchment[300]
        }
      }
    },
    MuiDialogActions: {
      styleOverrides: {
        root: {
          padding: 32,
          gap: 12
        }
      }
    },
    MuiMenu: {
      styleOverrides: {
        paper: {
          borderRadius: t.radius.lg,
          backgroundColor: "#151A11",
          border: `1px solid ${t.border.soft}`,
          boxShadow: t.shadow.lg
        }
      }
    },
    MuiMenuItem: {
      styleOverrides: {
        root: {
          borderRadius: t.radius.sm,
          margin: "2px 6px",
          "&:hover": {
            background: "rgba(243,236,222,.06)"
          },
          "&.Mui-selected": {
            background: "rgba(232,169,74,.14)",
            color: t.lantern[300]
          }
        }
      }
    },
    MuiTooltip: {
      styleOverrides: {
        tooltip: {
          backgroundColor: t.bark[800],
          border: `1px solid ${t.border.timber}`,
          color: t.parchment[100],
          fontSize: "0.78125rem",
          borderRadius: t.radius.sm,
          padding: "6px 10px"
        },
        arrow: {
          color: t.bark[800]
        }
      }
    },
    MuiTabs: {
      styleOverrides: {
        indicator: {
          backgroundColor: t.lantern[400],
          height: 2,
          borderRadius: t.radius.pill
        }
      }
    },
    MuiTab: {
      styleOverrides: {
        root: {
          textTransform: "none",
          fontFamily: t.font.body,
          color: t.parchment[400],
          "&.Mui-selected": {
            color: t.parchment[100]
          }
        }
      }
    },
    MuiDivider: {
      styleOverrides: {
        root: {
          borderColor: t.border.soft
        }
      }
    },
    MuiAvatar: {
      styleOverrides: {
        root: {
          borderRadius: t.radius.organicSoft,
          background: `linear-gradient(160deg, ${t.bark[600]}, ${t.loam[700]})`,
          border: `1px solid ${t.border.timber}`,
          color: t.parchment[300]
        }
      }
    },
    MuiAlert: {
      styleOverrides: {
        root: {
          borderRadius: t.radius.lg,
          border: `1px solid ${t.border.soft}`
        },
        standardSuccess: {
          background: "rgba(143,178,92,.16)",
          color: t.moss[300]
        },
        standardError: {
          background: "rgba(194,84,58,.16)",
          color: t.ember[400]
        },
        standardWarning: {
          background: "rgba(232,169,74,.16)",
          color: t.lantern[300]
        },
        standardInfo: {
          background: "rgba(95,169,163,.16)",
          color: t.fen[400]
        }
      }
    },
    MuiTypography: {
      defaultProps: {
        variantMapping: {
          subtitle2: "span",
          overline: "span"
        }
      }
    }
  }
};
Object.assign(__ds_scope, { goblinPubTokens, goblinPubThemeOptions, __ds_default_mui_goblinPubTheme_1g9wgxg: goblinPubThemeOptions });
})(); } catch (e) { __ds_ns.__errors.push({ path: "mui/goblinPubTheme.js", error: String((e && e.message) || e) }); }

// ui_kits/goblin-pub-app/AppShell.jsx
try { (() => {
(() => {
  const {
    IconButton,
    Icon,
    Badge
  } = window.GoblinPubDesignSystem_dfb40c;
  function Rail({
    view,
    onView
  }) {
    const items = [["session", "beer", "Session"], ["party", "users", "Party"], ["map", "map", "Map"], ["notes", "scroll-text", "Notes"]];
    return /*#__PURE__*/React.createElement("nav", {
      style: {
        width: 68,
        flex: "0 0 auto",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 8,
        padding: "18px 0",
        background: "var(--surface-sunken)",
        borderRight: "1px solid var(--border-hairline)"
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        width: 38,
        height: 38,
        display: "grid",
        placeItems: "center",
        borderRadius: "var(--radius-organic-soft)",
        background: "linear-gradient(160deg, var(--bark-600), var(--loam-800))",
        border: "1px solid var(--border-timber)",
        marginBottom: 10
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        fontFamily: "var(--font-smallcaps)",
        fontSize: 15,
        color: "var(--lantern-300)"
      }
    }, "GP")), items.map(([id, icon, label]) => /*#__PURE__*/React.createElement(IconButton, {
      key: id,
      icon: icon,
      label: label,
      active: view === id,
      onClick: () => onView(id)
    })), /*#__PURE__*/React.createElement("div", {
      style: {
        marginTop: "auto"
      }
    }, /*#__PURE__*/React.createElement(IconButton, {
      icon: "settings",
      label: "Settings"
    })));
  }
  function TopBar({
    title,
    subtitle,
    right
  }) {
    return /*#__PURE__*/React.createElement("header", {
      style: {
        display: "flex",
        alignItems: "center",
        gap: 16,
        padding: "14px 24px",
        borderBottom: "1px solid var(--border-hairline)",
        background: "var(--surface-sunken)"
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        minWidth: 0
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        font: "var(--weight-bold) 1.125rem/1.2 var(--font-display)",
        color: "var(--text-primary)"
      }
    }, title), subtitle ? /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: "var(--text-micro)",
        color: "var(--text-muted)"
      }
    }, subtitle) : null), /*#__PURE__*/React.createElement("div", {
      style: {
        marginLeft: "auto",
        display: "flex",
        alignItems: "center",
        gap: 10
      }
    }, right));
  }
  function AppShell({
    view,
    onView,
    title,
    subtitle,
    topRight,
    children
  }) {
    return /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        height: "100%",
        background: "var(--surface-app)",
        color: "var(--text-primary)",
        fontFamily: "var(--font-body)"
      }
    }, /*#__PURE__*/React.createElement(Rail, {
      view: view,
      onView: onView
    }), /*#__PURE__*/React.createElement("div", {
      style: {
        flex: 1,
        minWidth: 0,
        display: "flex",
        flexDirection: "column"
      }
    }, /*#__PURE__*/React.createElement(TopBar, {
      title: title,
      subtitle: subtitle,
      right: topRight
    }), /*#__PURE__*/React.createElement("div", {
      style: {
        flex: 1,
        minHeight: 0
      }
    }, children)));
  }
  Object.assign(window, {
    AppShell,
    Rail,
    TopBar
  });
})();
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/goblin-pub-app/AppShell.jsx", error: String((e && e.message) || e) }); }

// ui_kits/goblin-pub-app/CampaignHome.jsx
try { (() => {
(() => {
  const {
    Card,
    Button,
    Badge,
    Icon,
    Input,
    SceneImage
  } = window.GoblinPubDesignSystem_dfb40c;
  function CampaignHome({
    onOpen,
    onNew
  }) {
    return /*#__PURE__*/React.createElement("div", {
      style: {
        height: "100%",
        overflow: "auto",
        padding: "28px 32px",
        display: "grid",
        gap: 24,
        alignContent: "start"
      }
    }, /*#__PURE__*/React.createElement(SceneImage, {
      height: 190,
      chapter: "Continue",
      caption: "The Rotting Stump \xB7 Session 6"
    }, "Cover art slot \u2014 supply real artwork"), /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        alignItems: "center",
        gap: 14
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        fontFamily: "var(--font-smallcaps)",
        fontSize: "var(--text-micro)",
        letterSpacing: "var(--ls-label)",
        color: "var(--text-muted)"
      }
    }, "YOUR CAMPAIGNS"), /*#__PURE__*/React.createElement("span", {
      style: {
        flex: 1,
        height: 1,
        background: "var(--border-soft)"
      }
    }), /*#__PURE__*/React.createElement(Button, {
      size: "sm",
      icon: "plus",
      onClick: onNew
    }, "New campaign")), /*#__PURE__*/React.createElement("div", {
      style: {
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
        gap: 16
      }
    }, window.CAMPAIGNS.map(c => /*#__PURE__*/React.createElement(Card, {
      key: c.id,
      tone: "raised",
      lantern: c.id === "stump",
      onClick: () => onOpen(c),
      style: {
        cursor: "pointer"
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        alignItems: "center",
        gap: 10,
        marginBottom: 8
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "book-open",
      size: 16,
      color: "var(--lantern-400)"
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        font: "var(--weight-bold) 1.125rem/1.2 var(--font-display)"
      }
    }, c.title)), /*#__PURE__*/React.createElement("p", {
      style: {
        margin: "0 0 14px",
        fontSize: "var(--text-small)",
        color: "var(--text-secondary)"
      }
    }, c.blurb), /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        gap: 8,
        flexWrap: "wrap"
      }
    }, /*#__PURE__*/React.createElement(Badge, {
      tone: "moss"
    }, c.tone), /*#__PURE__*/React.createElement(Badge, {
      icon: "scroll-text"
    }, c.sessions, " sessions"), /*#__PURE__*/React.createElement(Badge, null, c.last))))));
  }
  Object.assign(window, {
    CampaignHome
  });
})();
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/goblin-pub-app/CampaignHome.jsx", error: String((e && e.message) || e) }); }

// ui_kits/goblin-pub-app/CharacterSheet.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
(() => {
  const {
    Card,
    Badge,
    Button,
    Icon,
    AbilityScore,
    ResourceBar,
    Divider,
    Tag,
    Field,
    Textarea
  } = window.GoblinPubDesignSystem_dfb40c;
  function CharacterSheet({
    character,
    onBack
  }) {
    const c = character;
    return /*#__PURE__*/React.createElement("div", {
      style: {
        height: "100%",
        overflow: "auto",
        padding: "26px 32px"
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        maxWidth: 900,
        margin: "0 auto",
        display: "grid",
        gap: 18
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        alignItems: "center",
        gap: 12
      }
    }, /*#__PURE__*/React.createElement(Button, {
      variant: "ghost",
      size: "sm",
      icon: "chevron-left",
      onClick: onBack
    }, "Back to session")), /*#__PURE__*/React.createElement(Card, {
      tone: "raised",
      lantern: true,
      padding: "var(--sp-7)"
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        gap: 18,
        alignItems: "center"
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        width: 76,
        height: 76,
        borderRadius: "var(--radius-organic-soft)",
        background: "linear-gradient(160deg, var(--bark-600), var(--loam-700))",
        border: "1px solid var(--border-timber)",
        display: "grid",
        placeItems: "center"
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "user",
      size: 28,
      color: "var(--parchment-400)"
    })), /*#__PURE__*/React.createElement("div", {
      style: {
        flex: 1
      }
    }, /*#__PURE__*/React.createElement("h1", {
      style: {
        font: "var(--weight-bold) 2rem/1.14 var(--font-display)"
      }
    }, c.name), /*#__PURE__*/React.createElement("div", {
      style: {
        color: "var(--text-muted)",
        fontSize: "var(--text-small)"
      }
    }, c.subtitle)), /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        gap: 8
      }
    }, /*#__PURE__*/React.createElement(Badge, {
      icon: "shield"
    }, "AC ", c.ac), /*#__PURE__*/React.createElement(Badge, {
      icon: "footprints"
    }, "Init +", c.initiative))), /*#__PURE__*/React.createElement("div", {
      style: {
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: 18,
        marginTop: 20
      }
    }, /*#__PURE__*/React.createElement(ResourceBar, {
      label: "Hit points",
      value: c.hp.value,
      max: c.hp.max,
      kind: "hp"
    }), /*#__PURE__*/React.createElement(ResourceBar, {
      label: "Experience",
      value: 2400,
      max: 6500,
      kind: "xp",
      suffix: "XP"
    }))), /*#__PURE__*/React.createElement("div", {
      style: {
        display: "grid",
        gridTemplateColumns: "1.4fr 1fr",
        gap: 16,
        alignItems: "start"
      }
    }, /*#__PURE__*/React.createElement(Card, {
      title: "Abilities"
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: "grid",
        gridTemplateColumns: "repeat(6,1fr)",
        gap: 8
      }
    }, c.abilities.map(a => /*#__PURE__*/React.createElement(AbilityScore, _extends({
      key: a.abbr
    }, a)))), /*#__PURE__*/React.createElement(Divider, {
      label: "Proficiencies"
    }), /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        gap: 8,
        flexWrap: "wrap"
      }
    }, ["Stealth", "Sleight of Hand", "Deception", "Thieves' tools", "Shortbow"].map(t => /*#__PURE__*/React.createElement(Tag, {
      key: t
    }, t)))), /*#__PURE__*/React.createElement(Card, {
      tone: "timber",
      title: "Pack"
    }, /*#__PURE__*/React.createElement("ul", {
      style: {
        margin: 0,
        padding: 0,
        listStyle: "none",
        display: "grid",
        gap: 8,
        fontSize: "var(--text-small)",
        color: "var(--text-secondary)"
      }
    }, [["backpack", "Rope, 50 ft"], ["flame", "Tinderbox"], ["beer", "Stolen tankard"], ["wand-sparkles", "Unlabelled vial"]].map(([i, l]) => /*#__PURE__*/React.createElement("li", {
      key: l,
      style: {
        display: "flex",
        gap: 10,
        alignItems: "center"
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: i,
      size: 15,
      color: "var(--bark-400)"
    }), l))))), /*#__PURE__*/React.createElement(Card, {
      tone: "sunken"
    }, /*#__PURE__*/React.createElement(Field, {
      label: "Notes the DM can see"
    }, /*#__PURE__*/React.createElement(Textarea, {
      rows: 3,
      value: "Owes the ladle-goblin a favour. Will not say why.",
      onChange: () => {}
    })))));
  }
  Object.assign(window, {
    CharacterSheet
  });
})();
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/goblin-pub-app/CharacterSheet.jsx", error: String((e && e.message) || e) }); }

// ui_kits/goblin-pub-app/NewSessionDialog.jsx
try { (() => {
(() => {
  const {
    Dialog,
    Button,
    Field,
    Input,
    Select,
    Checkbox,
    Switch,
    Tag
  } = window.GoblinPubDesignSystem_dfb40c;
  function NewSessionDialog({
    open,
    onClose,
    onStart
  }) {
    const [name, setName] = React.useState("The Rotting Stump");
    const [tone, setTone] = React.useState("Comedic");
    const [dice, setDice] = React.useState(true);
    const [homebrew, setHomebrew] = React.useState(false);
    return /*#__PURE__*/React.createElement(Dialog, {
      open: open,
      onClose: onClose,
      title: "Start a session",
      footer: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Button, {
        variant: "ghost",
        onClick: onClose
      }, "Cancel"), /*#__PURE__*/React.createElement(Button, {
        icon: "flame",
        onClick: onStart
      }, "Light the lantern"))
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: "grid",
        gap: 16
      }
    }, /*#__PURE__*/React.createElement(Field, {
      label: "Campaign",
      hint: "Pick up where you left off, or name a new one."
    }, /*#__PURE__*/React.createElement(Input, {
      value: name,
      onChange: setName,
      icon: "book-open"
    })), /*#__PURE__*/React.createElement(Field, {
      label: "Tone"
    }, /*#__PURE__*/React.createElement(Select, {
      value: tone,
      onChange: setTone,
      options: ["Grim", "Heroic", "Comedic", "Uncanny"]
    })), /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        gap: 8,
        flexWrap: "wrap"
      }
    }, ["Tavern", "Investigation", "Low combat"].map(t => /*#__PURE__*/React.createElement(Tag, {
      key: t,
      selected: t === "Tavern",
      onClick: () => {}
    }, t))), /*#__PURE__*/React.createElement(Switch, {
      checked: dice,
      onChange: setDice,
      label: "Roll dice for the party"
    }), /*#__PURE__*/React.createElement(Checkbox, {
      checked: homebrew,
      onChange: setHomebrew,
      label: "Allow homebrew rules from my notes"
    })));
  }
  Object.assign(window, {
    NewSessionDialog
  });
})();
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/goblin-pub-app/NewSessionDialog.jsx", error: String((e && e.message) || e) }); }

// ui_kits/goblin-pub-app/SessionView.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
(() => {
  const {
    ChatMessage,
    ChatComposer,
    TypingIndicator,
    DiceRoll,
    Divider,
    PlayerStatCard,
    Card,
    Badge,
    Button,
    Icon,
    SceneImage
  } = window.GoblinPubDesignSystem_dfb40c;
  function PartyRail({
    party,
    activeId,
    onSelect
  }) {
    return /*#__PURE__*/React.createElement("aside", {
      style: {
        width: 300,
        flex: "0 0 auto",
        borderLeft: "1px solid var(--border-hairline)",
        background: "var(--surface-sunken)",
        padding: 18,
        overflow: "auto",
        display: "grid",
        gap: 12,
        alignContent: "start"
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between"
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        fontFamily: "var(--font-smallcaps)",
        fontSize: "var(--text-micro)",
        letterSpacing: "var(--ls-label)",
        color: "var(--text-muted)"
      }
    }, "PARTY \xB7 ROUND 3"), /*#__PURE__*/React.createElement(Icon, {
      name: "users",
      size: 14,
      color: "var(--text-faint)"
    })), party.map(p => /*#__PURE__*/React.createElement(PlayerStatCard, _extends({
      key: p.id
    }, p, {
      compact: true,
      active: p.id === activeId,
      onClick: () => onSelect(p.id)
    }))), /*#__PURE__*/React.createElement(Card, {
      tone: "sunken",
      padding: "14px"
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontFamily: "var(--font-smallcaps)",
        fontSize: "var(--text-micro)",
        letterSpacing: "var(--ls-label)",
        color: "var(--text-muted)",
        marginBottom: 8
      }
    }, "SCENE"), /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        gap: 8,
        flexWrap: "wrap"
      }
    }, /*#__PURE__*/React.createElement(Badge, {
      tone: "accent",
      icon: "flame"
    }, "Torchlit"), /*#__PURE__*/React.createElement(Badge, {
      icon: "beer"
    }, "Tavern"), /*#__PURE__*/React.createElement(Badge, {
      tone: "magic",
      icon: "sparkles"
    }, "Wild magic"))));
  }
  function Log({
    messages,
    thinking
  }) {
    const end = React.useRef(null);
    React.useEffect(() => {
      if (end.current) end.current.parentNode.scrollTop = end.current.parentNode.scrollHeight;
    }, [messages.length, thinking]);
    return /*#__PURE__*/React.createElement("div", {
      style: {
        flex: 1,
        minHeight: 0,
        overflow: "auto",
        padding: "22px 28px 8px"
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        maxWidth: 760,
        margin: "0 auto",
        display: "grid",
        gap: 14
      }
    }, /*#__PURE__*/React.createElement(SceneImage, {
      height: 170,
      chapter: "Chapter 2",
      caption: "The Rotting Stump, past midnight"
    }, "Scene art slot \u2014 supply real artwork"), /*#__PURE__*/React.createElement(Divider, {
      label: "Session 6 \xB7 Round 3"
    }), messages.map(m => m.role === "roll" ? /*#__PURE__*/React.createElement("div", {
      key: m.id,
      style: {
        display: "flex",
        justifyContent: "center"
      }
    }, /*#__PURE__*/React.createElement(DiceRoll, m)) : /*#__PURE__*/React.createElement(ChatMessage, {
      key: m.id,
      role: m.role,
      author: m.author,
      time: m.time
    }, m.text)), thinking ? /*#__PURE__*/React.createElement(TypingIndicator, null) : null, /*#__PURE__*/React.createElement("div", {
      ref: end
    })));
  }
  function SessionView({
    campaign,
    party,
    activeId,
    onSelect
  }) {
    const [messages, setMessages] = React.useState(window.OPENING);
    const [draft, setDraft] = React.useState("");
    const [thinking, setThinking] = React.useState(false);
    const send = () => {
      if (!draft.trim()) return;
      const text = draft;
      setDraft("");
      setMessages(m => [...m, {
        id: Date.now(),
        role: "player",
        author: "Brakka",
        time: "21:0" + (m.length + 2),
        text
      }]);
      setThinking(true);
      setTimeout(() => {
        setThinking(false);
        setMessages(m => [...m, {
          id: Date.now() + 1,
          role: "roll",
          label: "Insight",
          notation: "1d20+2",
          breakdown: "16 + 2",
          total: 18,
          outcome: "neutral"
        }, {
          id: Date.now() + 2,
          role: "dm",
          author: "The Dungeon Master",
          time: "21:09",
          text: window.REPLIES[m.length % window.REPLIES.length]
        }]);
      }, 1400);
    };
    return /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        height: "100%"
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        flex: 1,
        minWidth: 0,
        display: "flex",
        flexDirection: "column",
        backgroundImage: "var(--wash-moss)"
      }
    }, /*#__PURE__*/React.createElement(Log, {
      messages: messages,
      thinking: thinking
    }), /*#__PURE__*/React.createElement("div", {
      style: {
        padding: "8px 28px 22px"
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        maxWidth: 760,
        margin: "0 auto"
      }
    }, /*#__PURE__*/React.createElement(ChatComposer, {
      value: draft,
      onChange: setDraft,
      onSend: send
    })))), /*#__PURE__*/React.createElement(PartyRail, {
      party: party,
      activeId: activeId,
      onSelect: onSelect
    }));
  }
  Object.assign(window, {
    SessionView,
    PartyRail,
    Log
  });
})();
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/goblin-pub-app/SessionView.jsx", error: String((e && e.message) || e) }); }

// ui_kits/goblin-pub-app/data.jsx
try { (() => {
const PARTY = [{
  id: "brakka",
  name: "Brakka Nine-Fingers",
  subtitle: "Goblin Rogue · Level 4",
  hp: {
    value: 24,
    max: 32
  },
  ac: 15,
  initiative: 3,
  conditions: [],
  abilities: [{
    abbr: "STR",
    score: 9
  }, {
    abbr: "DEX",
    score: 18
  }, {
    abbr: "CON",
    score: 13
  }, {
    abbr: "INT",
    score: 12
  }, {
    abbr: "WIS",
    score: 11
  }, {
    abbr: "CHA",
    score: 16
  }]
}, {
  id: "ysolde",
  name: "Ysolde Ashwake",
  subtitle: "Human Cleric · Level 4",
  hp: {
    value: 29,
    max: 30
  },
  ac: 18,
  initiative: 1,
  conditions: [],
  abilities: [{
    abbr: "STR",
    score: 14
  }, {
    abbr: "DEX",
    score: 10
  }, {
    abbr: "CON",
    score: 15
  }, {
    abbr: "INT",
    score: 11
  }, {
    abbr: "WIS",
    score: 18
  }, {
    abbr: "CHA",
    score: 13
  }]
}, {
  id: "murk",
  name: "Murk",
  subtitle: "Half-orc Druid · Level 3",
  hp: {
    value: 8,
    max: 27
  },
  ac: 13,
  initiative: 2,
  conditions: ["Poisoned"],
  abilities: [{
    abbr: "STR",
    score: 12
  }, {
    abbr: "DEX",
    score: 14
  }, {
    abbr: "CON",
    score: 16
  }, {
    abbr: "INT",
    score: 10
  }, {
    abbr: "WIS",
    score: 17
  }, {
    abbr: "CHA",
    score: 9
  }]
}, {
  id: "pell",
  name: "Pell Tumbleweed",
  subtitle: "Halfling Bard · Level 4",
  hp: {
    value: 22,
    max: 26
  },
  ac: 14,
  initiative: 4,
  conditions: [],
  abilities: [{
    abbr: "STR",
    score: 8
  }, {
    abbr: "DEX",
    score: 16
  }, {
    abbr: "CON",
    score: 12
  }, {
    abbr: "INT",
    score: 13
  }, {
    abbr: "WIS",
    score: 11
  }, {
    abbr: "CHA",
    score: 18
  }]
}];
const CAMPAIGNS = [{
  id: "stump",
  title: "The Rotting Stump",
  tone: "Comedic",
  sessions: 6,
  last: "Two nights ago",
  blurb: "A goblin pub on the wrong side of the Blackmire has started serving something that talks back."
}, {
  id: "mire",
  title: "Down the Blackmire",
  tone: "Grim",
  sessions: 12,
  last: "Last week",
  blurb: "The bog has been rising for a season, and the drowned keep are no longer drowned."
}, {
  id: "hollow",
  title: "Hollowsong",
  tone: "Uncanny",
  sessions: 2,
  last: "A month ago",
  blurb: "Every child in the valley hums the same four notes and none of them remember learning it."
}];
const OPENING = [{
  id: 1,
  role: "dm",
  author: "The Dungeon Master",
  time: "21:02",
  text: "The Rotting Stump leans over the path like it is listening. Warm light bleeds through the shutters, and somebody inside is losing an argument about a barrel."
}, {
  id: 2,
  role: "player",
  author: "Brakka",
  time: "21:04",
  text: "I push the door open with my boot and walk in like I own the place."
}, {
  id: 3,
  role: "system",
  text: "Intimidation check · DC 13"
}, {
  id: 4,
  role: "roll",
  label: "Intimidation",
  notation: "1d20+5",
  breakdown: "12 + 5",
  total: 17,
  outcome: "neutral"
}, {
  id: 5,
  role: "dm",
  author: "The Dungeon Master",
  time: "21:05",
  text: "Three goblins look up. The one holding the ladle decides, quickly and visibly, that you are a guest and not a problem. The other two keep arguing."
}];
const REPLIES = ["The ladle-goblin pours you something amber and does not make eye contact. Behind the bar, a cabinet rattles once and goes still.", "The arguing pair fall quiet. One of them slides a folded map across the table, weighted down with a tooth that is far too large to be a goblin's.", "Outside, the woods take a slow breath. Something wet moves past the shutters and the light dims for the length of a heartbeat."];
Object.assign(window, {
  PARTY,
  CAMPAIGNS,
  OPENING,
  REPLIES
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/goblin-pub-app/data.jsx", error: String((e && e.message) || e) }); }

__ds_ns.ChatComposer = __ds_scope.ChatComposer;

__ds_ns.ChatMessage = __ds_scope.ChatMessage;

__ds_ns.DiceRoll = __ds_scope.DiceRoll;

__ds_ns.TypingIndicator = __ds_scope.TypingIndicator;

__ds_ns.Badge = __ds_scope.Badge;

__ds_ns.Button = __ds_scope.Button;

__ds_ns.Card = __ds_scope.Card;

__ds_ns.Dialog = __ds_scope.Dialog;

__ds_ns.Divider = __ds_scope.Divider;

__ds_ns.Icon = __ds_scope.Icon;

__ds_ns.IconButton = __ds_scope.IconButton;

__ds_ns.Tag = __ds_scope.Tag;

__ds_ns.Checkbox = __ds_scope.Checkbox;

__ds_ns.Field = __ds_scope.Field;

__ds_ns.Input = __ds_scope.Input;

__ds_ns.Select = __ds_scope.Select;

__ds_ns.Switch = __ds_scope.Switch;

__ds_ns.Textarea = __ds_scope.Textarea;

__ds_ns.AbilityScore = __ds_scope.AbilityScore;

__ds_ns.PlayerStatCard = __ds_scope.PlayerStatCard;

__ds_ns.ResourceBar = __ds_scope.ResourceBar;

__ds_ns.SceneImage = __ds_scope.SceneImage;

})();
