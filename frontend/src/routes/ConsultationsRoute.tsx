import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Icon from "@mui/material/Icon";
import IconButton from "@mui/material/IconButton";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import Paper from "@mui/material/Paper";
import Skeleton from "@mui/material/Skeleton";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link as RouterLink, useNavigate } from "react-router";

import { ConfirmDialog } from "../components/ConfirmDialog";
import { EmptyState } from "../components/EmptyState";
import { useChats, useCreateChat, useDeleteChat, type Chat } from "../hooks/useChats";

/**
 * The authenticated home: every consultation this user has had with the advisor,
 * last activity first, plus the one button that starts a new one.
 *
 * A consultation is **never** created on page load — the advisor speaks first,
 * and being greeted by a bot you did not ask for is exactly the experience this
 * screen avoids. "Ask the advisor" is therefore a deliberate action, and the
 * created chat opens directly on the advisor's incoming greeting.
 *
 * The list refreshes itself: an advisor reply landing in any conversation
 * arrives as an SSE invalidation, so rows reorder and the "replying…" hint
 * disappears without a reload. The disconnect warning is deliberately *not*
 * rendered here — a stale ordering is harmless and the banner would be noise on
 * the home screen.
 */

const SKELETON_ROW_COUNT = 4;

export function ConsultationsRoute() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();

  const chats = useChats();
  const createChat = useCreateChat();
  const deleteChat = useDeleteChat();

  // The chat awaiting confirmation; the dialog is mounted per opening so a
  // failure from an earlier attempt never greets the next one.
  const [chatToDelete, setChatToDelete] = useState<Chat | null>(null);

  /** The chat's own title, or the placeholder for one that has none yet. */
  function displayTitle(chat: Chat): string {
    return chat.title === null || chat.title === ""
      ? t("consultations.list.untitled")
      : chat.title;
  }

  function startConsultation() {
    createChat.mutate(undefined, {
      onSuccess: (created) => {
        void navigate(`/consultations/${created.id}`);
      },
    });
  }

  function confirmDelete() {
    if (chatToDelete === null) {
      return;
    }

    deleteChat.mutate(
      { chatId: chatToDelete.id },
      { onSuccess: () => setChatToDelete(null) },
    );
  }

  const newConsultationButton = (
    <Button
      variant="contained"
      startIcon={
        createChat.isPending ? (
          <CircularProgress size={20} color="inherit" />
        ) : (
          <Icon>add_comment</Icon>
        )
      }
      disabled={createChat.isPending}
      onClick={startConsultation}
    >
      {t("consultations.list.newConsultation")}
    </Button>
  );

  function renderRow(chat: Chat) {
    return (
      <ListItem
        key={chat.id}
        disablePadding
        divider
        secondaryAction={
          <Stack direction="row" spacing={1} alignItems="center">
            {chat.activeOperationId !== null && (
              // Colour plus text, never colour alone.
              <Typography variant="caption" color="primary">
                {t("consultations.list.replying")}
              </Typography>
            )}
            <IconButton
              edge="end"
              aria-label={t("consultations.list.delete")}
              onClick={() => {
                deleteChat.reset();
                setChatToDelete(chat);
              }}
            >
              <Icon>delete</Icon>
            </IconButton>
          </Stack>
        }
      >
        <ListItemButton component={RouterLink} to={`/consultations/${chat.id}`}>
          <ListItemText
            primary={displayTitle(chat)}
            slotProps={{ primary: { noWrap: true } }}
            secondary={new Date(chat.updatedAt).toLocaleString(i18n.language, {
              dateStyle: "medium",
              timeStyle: "short",
            })}
          />
        </ListItemButton>
      </ListItem>
    );
  }

  function renderContent() {
    if (chats.isError) {
      return (
        <EmptyState
          icon="error"
          title={t("consultations.list.loadError")}
          body={t("common.errors.serverError")}
          action={
            <Button
              onClick={() => {
                void chats.refetch();
              }}
            >
              {t("common.retry")}
            </Button>
          }
        />
      );
    }

    // First load only: a background refetch (an SSE invalidation, above all)
    // keeps the current rows on screen — swapping live rows for skeletons on
    // every advisor reply would be unreadable.
    if (chats.isLoading) {
      return (
        <Paper variant="outlined">
          <List disablePadding>
            {Array.from({ length: SKELETON_ROW_COUNT }, (_unused, index) => (
              <ListItem key={index} divider>
                <ListItemText
                  primary={<Skeleton variant="text" width="60%" />}
                  secondary={<Skeleton variant="text" width="30%" />}
                />
              </ListItem>
            ))}
          </List>
        </Paper>
      );
    }

    const rows = chats.data ?? [];

    if (rows.length === 0) {
      return (
        <EmptyState
          icon="forum"
          title={t("consultations.list.emptyTitle")}
          body={t("consultations.list.emptyBody")}
          action={newConsultationButton}
        />
      );
    }

    return (
      <Paper variant="outlined">
        <List aria-label={t("consultations.list.listLabel")} disablePadding>
          {rows.map(renderRow)}
        </List>
      </Paper>
    );
  }

  return (
    <>
      <Stack
        direction="row"
        sx={{
          mb: 2,
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: 2,
        }}
      >
        <Typography variant="h4" component="h1">
          {t("consultations.list.title")}
        </Typography>
        {newConsultationButton}
      </Stack>
      {renderContent()}
      {chatToDelete !== null && (
        <ConfirmDialog
          title={t("consultations.list.deleteConfirmTitle")}
          body={t("consultations.list.deleteConfirmBody", {
            title: displayTitle(chatToDelete),
          })}
          confirmLabel={t("consultations.list.deleteConfirm")}
          confirmColor="error"
          isPending={deleteChat.isPending}
          hasError={deleteChat.isError}
          onConfirm={confirmDelete}
          onClose={() => setChatToDelete(null)}
        />
      )}
      {/* Nothing else on the page changes when starting a consultation fails,
          so the failure needs a surface of its own. */}
      <Snackbar
        open={createChat.isError}
        autoHideDuration={6000}
        onClose={() => createChat.reset()}
      >
        <Alert severity="error" onClose={() => createChat.reset()}>
          {t("consultations.list.createError")}
        </Alert>
      </Snackbar>
    </>
  );
}
