import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Trash2, UserPlus } from "lucide-react";
import { api, type CreateUserBody } from "../lib/api";
import type { UserAccount, UserRole } from "../lib/types";
import { EmptyState } from "./EmptyState";
import { ViewSkeleton } from "./ViewSkeleton";
import { parseServerDate } from "../lib/dates";

const ROLES: UserRole[] = ["admin", "manager", "viewer"];

const EMPTY_FORM: CreateUserBody = { username: "", display_name: "", role: "viewer", temp_password: "" };

function formatLastLogin(value: string | null): string {
  if (!value) return "—";
  return parseServerDate(value).toLocaleString();
}

export function UsersView({ token, currentUsername }: { token: string; currentUsername: string }) {
  const queryClient = useQueryClient();
  const usersQuery = useQuery({ queryKey: ["users"], queryFn: () => api.users.list(token) });
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<CreateUserBody>(EMPTY_FORM);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["users"] });

  function run(action: Promise<unknown>) {
    setError(null);
    action.then(invalidate).catch((err) => setError(err instanceof Error ? err.message : "Action failed"));
  }

  const createMut = useMutation({
    mutationFn: () => api.users.create(token, form),
    onSuccess: () => {
      setForm(EMPTY_FORM);
      setError(null);
      invalidate();
    },
    onError: (err: unknown) => setError(err instanceof Error ? err.message : "Could not create user")
  });

  function submitCreate(event: FormEvent) {
    event.preventDefault();
    createMut.mutate();
  }

  if (usersQuery.isLoading) return <ViewSkeleton />;
  if (usersQuery.error) {
    const message = usersQuery.error instanceof Error ? usersQuery.error.message : "Unable to load users";
    return <EmptyState title={message} />;
  }

  const users = usersQuery.data ?? [];

  return (
    <div className="users-view stack">
      <form className="card users-create" onSubmit={submitCreate}>
        <div className="section-header">
          <h2 className="h2">Add a user</h2>
        </div>
        <div className="users-create__grid">
          <label className="field">
            Username
            <input
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              autoComplete="off"
              placeholder="cody"
            />
          </label>
          <label className="field">
            Display name
            <input
              value={form.display_name}
              onChange={(e) => setForm({ ...form, display_name: e.target.value })}
              autoComplete="off"
              placeholder="Cody"
            />
          </label>
          <label className="field">
            Role
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as UserRole })}>
              {ROLES.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            Temp password
            <input
              value={form.temp_password}
              onChange={(e) => setForm({ ...form, temp_password: e.target.value })}
              autoComplete="off"
              placeholder="at least 6 characters"
            />
          </label>
        </div>
        {error ? <p className="form-error">{error}</p> : null}
        <button className="primary-button" disabled={createMut.isPending}>
          <UserPlus size={16} aria-hidden="true" /> {createMut.isPending ? "Creating" : "Create user"}
        </button>
        <p className="form-hint">New users must set their own password on first sign-in.</p>
      </form>

      <div className="card table-wrap">
        <table className="users-table">
          <thead>
            <tr>
              <th>User</th>
              <th>Role</th>
              <th>Status</th>
              <th>Last login</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <UserRow
                key={user.id}
                user={user}
                isSelf={user.username === currentUsername}
                onRole={(role) => run(api.users.update(token, user.id, { role }))}
                onToggleActive={() => run(api.users.update(token, user.id, { active: !user.active }))}
                onReset={() => {
                  const temp = window.prompt(`New temporary password for ${user.username}:`);
                  if (temp) run(api.users.resetPassword(token, user.id, temp));
                }}
                onDelete={() => {
                  if (window.confirm(`Delete ${user.username}? This cannot be undone.`)) {
                    run(api.users.remove(token, user.id));
                  }
                }}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function UserRow({
  user,
  isSelf,
  onRole,
  onToggleActive,
  onReset,
  onDelete
}: {
  user: UserAccount;
  isSelf: boolean;
  onRole: (role: UserRole) => void;
  onToggleActive: () => void;
  onReset: () => void;
  onDelete: () => void;
}) {
  return (
    <tr className={user.active ? "" : "is-disabled"}>
      <td>
        <div className="users-table__name">
          <strong>{user.display_name}</strong>
          <span className="muted">@{user.username}{isSelf ? " (you)" : ""}</span>
        </div>
      </td>
      <td>
        <select value={user.role} onChange={(e) => onRole(e.target.value as UserRole)} aria-label={`Role for ${user.username}`}>
          {ROLES.map((role) => (
            <option key={role} value={role}>
              {role}
            </option>
          ))}
        </select>
      </td>
      <td>
        <span className={`pill ${user.active ? "pill-active" : "pill-paused"}`}>
          <span className="pill__dot" /> {user.active ? "active" : "disabled"}
        </span>
        {user.must_change_password ? <span className="pill pill-needs_chase">temp pw</span> : null}
      </td>
      <td className="muted">{formatLastLogin(user.last_login_at)}</td>
      <td>
        <div className="users-table__actions">
          <button className="ghost-button compact" onClick={onReset} title="Reset password">
            <KeyRound size={15} aria-hidden="true" /> Reset
          </button>
          <button className="ghost-button compact" onClick={onToggleActive}>
            {user.active ? "Disable" : "Enable"}
          </button>
          <button
            className="ghost-button ghost-button--danger compact"
            onClick={onDelete}
            disabled={isSelf}
            title={isSelf ? "You cannot delete your own account" : "Delete user"}
          >
            <Trash2 size={15} aria-hidden="true" />
          </button>
        </div>
      </td>
    </tr>
  );
}
