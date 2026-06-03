import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Archive, ArchiveRestore, Plus, Trash2, X } from "lucide-react";
import { api } from "../lib/api";
import { parseServerDate } from "../lib/dates";
import type { ProjectCondition, ProjectLog, ProjectTask } from "../lib/types";

interface ProjectEditorProps {
  token: string;
  project: ProjectCondition | null;
  onClose: () => void;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function logTime(iso: string): string {
  const date = parseServerDate(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
}

export function ProjectEditor({ token, project, onClose }: ProjectEditorProps) {
  const queryClient = useQueryClient();
  const isEdit = project !== null;

  const [title, setTitle] = useState(project?.title ?? "");
  const [summary, setSummary] = useState(project?.summary ?? "");
  const [tasks, setTasks] = useState<ProjectTask[]>(project?.open_items ?? []);
  const [logs, setLogs] = useState<ProjectLog[]>(project?.logs ?? []);
  const [newLog, setNewLog] = useState("");
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const titleInputRef = useRef<HTMLInputElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);
  const submittingRef = useRef(false);
  // Snapshot of the editable fields at open time, to detect unsaved changes on close.
  const initialSnapshot = useRef(
    JSON.stringify({ title: project?.title ?? "", summary: project?.summary ?? "", tasks: project?.open_items ?? [] })
  );
  const archived = project?.active === false;

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["project-conditions"] });

  const saveMutation = useMutation({
    mutationFn: () => {
      const open_items = tasks
        .map((task) => ({ text: task.text.trim(), done: task.done }))
        .filter((task) => task.text.length > 0);
      if (isEdit && project) {
        return api.updateProject(token, project.topic_id, {
          title: title.trim(),
          summary: summary.trim(),
          open_items
        });
      }
      return api.createProject(token, { title: title.trim(), summary: summary.trim(), open_items });
    },
    onSuccess: async () => {
      await invalidate();
      onClose();
    },
    onSettled: () => {
      submittingRef.current = false;
    }
  });

  const archiveMutation = useMutation({
    mutationFn: () => {
      if (!project) throw new Error("No project to archive");
      // Toggle: an archived project is restored (active:true); an active one is archived.
      return api.updateProject(token, project.topic_id, { active: archived });
    },
    onSuccess: async () => {
      await invalidate();
      onClose();
    }
  });

  const deleteMutation = useMutation({
    mutationFn: () => {
      if (!project) throw new Error("No project to delete");
      return api.deleteProject(token, project.topic_id);
    },
    onSuccess: async () => {
      await invalidate();
      onClose();
    }
  });

  const addLogMutation = useMutation({
    mutationFn: (body: string) => {
      if (!project) throw new Error("No project for log");
      return api.addProjectLog(token, project.topic_id, body);
    },
    onSuccess: async (updated) => {
      setLogs(updated.logs);
      setNewLog("");
      await invalidate();
    }
  });

  const deleteLogMutation = useMutation({
    mutationFn: (logId: number) => {
      if (!project) throw new Error("No project for log");
      return api.deleteProjectLog(token, project.topic_id, logId);
    },
    onSuccess: async (updated) => {
      setLogs(updated.logs);
      await invalidate();
    }
  });

  const busy =
    saveMutation.isPending ||
    archiveMutation.isPending ||
    deleteMutation.isPending ||
    addLogMutation.isPending ||
    deleteLogMutation.isPending;

  // Focus management: remember the trigger, focus the title, restore on close.
  useEffect(() => {
    previouslyFocused.current = document.activeElement as HTMLElement | null;
    titleInputRef.current?.focus();
    return () => {
      previouslyFocused.current?.focus?.();
    };
  }, []);

  // Escape to close + focus trap (Tab cycling within the dialog).
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.stopPropagation();
        requestCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const dialog = dialogRef.current;
      if (!dialog) return;
      const focusable = Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (el) => el.offsetParent !== null || el === document.activeElement
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const activeEl = document.activeElement;
      if (event.shiftKey && activeEl === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && activeEl === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", onKeyDown, true);
    return () => document.removeEventListener("keydown", onKeyDown, true);
  }, [onClose]);

  function addTask() {
    setTasks((prev) => [...prev, { text: "", done: false }]);
  }
  function updateTaskText(index: number, text: string) {
    setTasks((prev) => prev.map((task, i) => (i === index ? { ...task, text } : task)));
  }
  function toggleTaskDone(index: number) {
    setTasks((prev) => prev.map((task, i) => (i === index ? { ...task, done: !task.done } : task)));
  }
  function removeTask(index: number) {
    setTasks((prev) => prev.filter((_, i) => i !== index));
  }

  const isDirty = () =>
    JSON.stringify({ title, summary, tasks }) !== initialSnapshot.current;

  function requestClose() {
    // Guard against losing unsaved title/summary/task edits on an accidental dismiss.
    if (isDirty() && !window.confirm("Discard unsaved changes?")) return;
    onClose();
  }
  const requestCloseRef = useRef(requestClose);
  requestCloseRef.current = requestClose;

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    // submittingRef closes the double-click window before isPending re-renders.
    if (!title.trim() || busy || submittingRef.current) return;
    submittingRef.current = true;
    saveMutation.mutate();
  }

  function submitLog() {
    const body = newLog.trim();
    if (!body || addLogMutation.isPending) return;
    addLogMutation.mutate(body);
  }

  const titleEmpty = title.trim().length === 0;
  const actionError =
    saveMutation.error ?? archiveMutation.error ?? deleteMutation.error ?? addLogMutation.error ?? deleteLogMutation.error;

  return (
    <div
      className="sheet-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) requestClose();
      }}
    >
      <div
        className="sheet-panel card"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        ref={dialogRef}
      >
        <header className="sheet-head">
          <h2 className="h2" id={titleId}>
            {isEdit ? "Edit project" : "New project"}
          </h2>
          <button
            type="button"
            className="icon-button"
            onClick={requestClose}
            aria-label="Close editor"
          >
            <X size={20} aria-hidden="true" />
          </button>
        </header>

        <form className="sheet-body" onSubmit={onSubmit}>
          <label className="field">
            Title
            <input
              ref={titleInputRef}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Project title"
              required
            />
          </label>

          <label className="field">
            Summary
            <textarea
              value={summary}
              onChange={(event) => setSummary(event.target.value)}
              placeholder="What's the current condition?"
              rows={3}
            />
          </label>

          <div className="field">
            <div className="field__head">
              <span>Tasks</span>
              <button type="button" className="ghost-button" onClick={addTask}>
                <Plus size={16} aria-hidden="true" /> Add task
              </button>
            </div>
            {tasks.length ? (
              <ul className="task-edit-list">
                {tasks.map((task, index) => (
                  <li className="task-edit-row" key={index}>
                    <label className="task-check">
                      <input
                        type="checkbox"
                        checked={task.done}
                        onChange={() => toggleTaskDone(index)}
                        aria-label={task.text ? `Mark "${task.text}" ${task.done ? "not done" : "done"}` : "Toggle task done"}
                      />
                    </label>
                    <input
                      className={`task-text-input${task.done ? " is-done" : ""}`}
                      value={task.text}
                      onChange={(event) => updateTaskText(index, event.target.value)}
                      placeholder="Task description"
                    />
                    <button
                      type="button"
                      className="icon-button icon-button--sm"
                      onClick={() => removeTask(index)}
                      aria-label="Remove task"
                    >
                      <Trash2 size={16} aria-hidden="true" />
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <small className="muted">No tasks yet</small>
            )}
          </div>

          {isEdit ? (
            <div className="field">
              <div className="field__head">
                <span>Log</span>
              </div>
              <div className="log-add">
                <input
                  value={newLog}
                  onChange={(event) => setNewLog(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      submitLog();
                    }
                  }}
                  placeholder="Add a timestamped entry"
                  aria-label="New log entry"
                />
                <button
                  type="button"
                  className="primary-button compact"
                  onClick={submitLog}
                  disabled={!newLog.trim() || addLogMutation.isPending}
                >
                  Add
                </button>
              </div>
              {logs.length ? (
                <ol className="log-timeline">
                  {logs.map((log) => (
                    <li className="log-row" key={log.id}>
                      <div className="log-row__main">
                        <time className="log-row__time" dateTime={log.created_at}>
                          {logTime(log.created_at)}
                        </time>
                        <p className="log-row__body">{log.body}</p>
                      </div>
                      <button
                        type="button"
                        className="icon-button icon-button--sm"
                        onClick={() => deleteLogMutation.mutate(log.id)}
                        disabled={deleteLogMutation.isPending}
                        aria-label="Delete log entry"
                      >
                        <Trash2 size={16} aria-hidden="true" />
                      </button>
                    </li>
                  ))}
                </ol>
              ) : (
                <small className="muted">No log entries yet</small>
              )}
            </div>
          ) : null}

          {actionError ? <p className="form-error">{errorMessage(actionError, "Something went wrong")}</p> : null}

          <footer className="sheet-foot">
            {isEdit ? (
              <div className="sheet-foot__danger">
                <button
                  type="button"
                  className="ghost-button"
                  onClick={() => archiveMutation.mutate()}
                  disabled={busy}
                >
                  {archived ? (
                    <>
                      <ArchiveRestore size={16} aria-hidden="true" /> Unarchive
                    </>
                  ) : (
                    <>
                      <Archive size={16} aria-hidden="true" /> Archive
                    </>
                  )}
                </button>
                {confirmingDelete ? (
                  <span className="confirm-delete">
                    <span className="muted">Delete permanently?</span>
                    <button
                      type="button"
                      className="danger-button compact"
                      onClick={() => deleteMutation.mutate()}
                      disabled={busy}
                    >
                      Delete
                    </button>
                    <button
                      type="button"
                      className="ghost-button"
                      onClick={() => setConfirmingDelete(false)}
                      disabled={busy}
                    >
                      Cancel
                    </button>
                  </span>
                ) : (
                  <button
                    type="button"
                    className="ghost-button ghost-button--danger"
                    onClick={() => setConfirmingDelete(true)}
                    disabled={busy}
                  >
                    <Trash2 size={16} aria-hidden="true" /> Delete
                  </button>
                )}
              </div>
            ) : (
              <span />
            )}
            <div className="sheet-foot__primary">
              <button type="button" className="ghost-button" onClick={requestClose} disabled={busy}>
                Cancel
              </button>
              <button type="submit" className="primary-button compact" disabled={titleEmpty || busy}>
                {saveMutation.isPending ? "Saving" : "Save"}
              </button>
            </div>
          </footer>
        </form>
      </div>
    </div>
  );
}
