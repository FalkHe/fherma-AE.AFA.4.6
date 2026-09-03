import Icon from "@mui/material/Icon";
import IconButton from "@mui/material/IconButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Tooltip from "@mui/material/Tooltip";
import { useColorScheme } from "@mui/material/styles";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { themeModes, type ThemeMode } from "../theme";

const modeIcons: Record<ThemeMode, string> = {
  system: "contrast",
  light: "light_mode",
  dark: "dark_mode",
};

/**
 * Selects the colour theme. `useColorScheme` writes the choice to
 * localStorage itself, so "system" is a real, persisted third option rather
 * than merely the initial default.
 */
export function ThemeModeToggle() {
  const { t } = useTranslation();
  const { mode, setMode } = useColorScheme();
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);

  // Rendered before ThemeProvider has resolved the stored mode; rendering
  // nothing here avoids showing the wrong icon for a frame.
  if (!mode) {
    return null;
  }

  return (
    <>
      <Tooltip title={t("themeMode.buttonLabel")}>
        <IconButton
          color="inherit"
          aria-label={t("themeMode.buttonLabel")}
          aria-haspopup="menu"
          aria-expanded={anchorEl !== null}
          onClick={(event) => setAnchorEl(event.currentTarget)}
        >
          <Icon>{modeIcons[mode]}</Icon>
        </IconButton>
      </Tooltip>
      <Menu
        anchorEl={anchorEl}
        open={anchorEl !== null}
        onClose={() => setAnchorEl(null)}
        aria-label={t("themeMode.menuLabel")}
      >
        {themeModes.map((themeMode) => (
          <MenuItem
            key={themeMode}
            selected={themeMode === mode}
            onClick={() => {
              setMode(themeMode);
              setAnchorEl(null);
            }}
          >
            <ListItemIcon>
              <Icon fontSize="small">{modeIcons[themeMode]}</Icon>
            </ListItemIcon>
            <ListItemText>{t(`themeMode.${themeMode}`)}</ListItemText>
          </MenuItem>
        ))}
      </Menu>
    </>
  );
}
