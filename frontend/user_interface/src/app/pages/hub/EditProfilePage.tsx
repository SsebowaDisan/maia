import { useEffect, useMemo, useState } from "react";

import {
  createMyCreatorProfile,
  getMyCreatorProfile,
  updateMyCreatorProfile,
  uploadMyCreatorAvatar,
  type CreatorProfileRecord,
} from "../../../api/client";

type EditProfilePageProps = {
  onNavigate: (path: string) => void;
};

type FormState = {
  username: string;
  display_name: string;
  bio: string;
  website_url: string;
  github_url: string;
  twitter_url: string;
};

function toFormState(profile: CreatorProfileRecord | null): FormState {
  return {
    username: String(profile?.username || "").trim(),
    display_name: String(profile?.display_name || "").trim(),
    bio: String(profile?.bio || "").trim(),
    website_url: String(profile?.website_url || "").trim(),
    github_url: String(profile?.github_url || "").trim(),
    twitter_url: String(profile?.twitter_url || "").trim(),
  };
}

export function EditProfilePage({ onNavigate }: EditProfilePageProps) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [avatarBusy, setAvatarBusy] = useState(false);
  const [error, setError] = useState("");
  const [profile, setProfile] = useState<CreatorProfileRecord | null>(null);
  const [exists, setExists] = useState(false);
  const [form, setForm] = useState<FormState>(() => toFormState(null));

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const mine = await getMyCreatorProfile();
        const hasProfile = Boolean(mine?.exists);
        setExists(hasProfile);
        const normalized = hasProfile ? mine : null;
        setProfile(normalized);
        setForm(toFormState(normalized));
      } catch (nextError) {
        setError(String(nextError || "Failed to load your profile."));
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  const isCreateMode = useMemo(() => !exists, [exists]);

  const saveProfile = async () => {
    setSaving(true);
    setError("");
    try {
      const payload = {
        display_name: form.display_name,
        bio: form.bio,
        website_url: form.website_url,
        github_url: form.github_url,
        twitter_url: form.twitter_url,
      };
      let nextProfile: CreatorProfileRecord;
      if (isCreateMode) {
        nextProfile = await createMyCreatorProfile({
          username: form.username,
          ...payload,
        });
        setExists(true);
      } else {
        nextProfile = await updateMyCreatorProfile(payload);
      }
      setProfile(nextProfile);
      const profileUsername = String(nextProfile.username || "").trim();
      if (profileUsername) {
        onNavigate(`/creators/${encodeURIComponent(profileUsername)}`);
      }
    } catch (nextError) {
      setError(String(nextError || "Failed to save profile."));
    } finally {
      setSaving(false);
    }
  };

  const uploadAvatar = async (file: File) => {
    setAvatarBusy(true);
    setError("");
    try {
      const result = await uploadMyCreatorAvatar(file);
      setProfile(result.profile);
    } catch (nextError) {
      setError(String(nextError || "Failed to upload avatar."));
    } finally {
      setAvatarBusy(false);
    }
  };

  if (loading) {
    return <p className="text-[14px] text-[#64748b]">Loading profile editor...</p>;
  }

  return (
    <div className="mx-auto max-w-[760px] rounded-[24px] border border-black/[0.08] bg-white p-6 shadow-[0_16px_30px_rgba(15,23,42,0.08)]">
      <h1 className="text-[28px] font-semibold tracking-[-0.03em] text-[#0f172a]">
        {isCreateMode ? "Create your creator profile" : "Edit your creator profile"}
      </h1>
      <p className="mt-2 text-[14px] text-[#667085]">
        This profile appears on your public creator page and your published agents and teams.
      </p>

      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <label className="space-y-1">
          <span className="text-[12px] font-semibold text-[#475467]">Username</span>
          <input
            value={form.username}
            onChange={(event) => setForm((previous) => ({ ...previous, username: event.target.value.toLowerCase() }))}
            disabled={!isCreateMode}
            placeholder="your-name"
            className="h-10 w-full rounded-xl border border-black/[0.1] px-3 text-[13px] text-[#111827] outline-none focus:border-[#6366f1] disabled:bg-[#f3f4f6]"
          />
        </label>
        <label className="space-y-1">
          <span className="text-[12px] font-semibold text-[#475467]">Display name</span>
          <input
            value={form.display_name}
            onChange={(event) => setForm((previous) => ({ ...previous, display_name: event.target.value }))}
            placeholder="Team Micrurus"
            className="h-10 w-full rounded-xl border border-black/[0.1] px-3 text-[13px] text-[#111827] outline-none focus:border-[#6366f1]"
          />
        </label>
      </div>

      <label className="mt-4 block space-y-1">
        <span className="text-[12px] font-semibold text-[#475467]">Bio</span>
        <textarea
          value={form.bio}
          onChange={(event) => setForm((previous) => ({ ...previous, bio: event.target.value }))}
          rows={4}
          placeholder="What do you build and who is it for?"
          className="w-full rounded-xl border border-black/[0.1] px-3 py-2 text-[13px] text-[#111827] outline-none focus:border-[#6366f1]"
        />
      </label>

      <div className="mt-4 grid gap-4 sm:grid-cols-3">
        <label className="space-y-1">
          <span className="text-[12px] font-semibold text-[#475467]">Website</span>
          <input
            value={form.website_url}
            onChange={(event) => setForm((previous) => ({ ...previous, website_url: event.target.value }))}
            className="h-10 w-full rounded-xl border border-black/[0.1] px-3 text-[13px] text-[#111827] outline-none focus:border-[#6366f1]"
          />
        </label>
        <label className="space-y-1">
          <span className="text-[12px] font-semibold text-[#475467]">GitHub</span>
          <input
            value={form.github_url}
            onChange={(event) => setForm((previous) => ({ ...previous, github_url: event.target.value }))}
            className="h-10 w-full rounded-xl border border-black/[0.1] px-3 text-[13px] text-[#111827] outline-none focus:border-[#6366f1]"
          />
        </label>
        <label className="space-y-1">
          <span className="text-[12px] font-semibold text-[#475467]">Twitter/X</span>
          <input
            value={form.twitter_url}
            onChange={(event) => setForm((previous) => ({ ...previous, twitter_url: event.target.value }))}
            className="h-10 w-full rounded-xl border border-black/[0.1] px-3 text-[13px] text-[#111827] outline-none focus:border-[#6366f1]"
          />
        </label>
      </div>

      <div className="mt-5 rounded-xl border border-black/[0.08] bg-[#f8fafc] p-4">
        <p className="text-[12px] font-semibold text-[#475467]">Avatar</p>
        <div className="mt-2 flex items-center gap-3">
          <div className="h-14 w-14 overflow-hidden rounded-xl bg-[#eef2ff]">
            {profile?.avatar_url ? <img src={profile.avatar_url} alt="Profile avatar" className="h-full w-full object-cover" /> : null}
          </div>
          <label className="inline-flex h-9 cursor-pointer items-center rounded-xl border border-black/[0.1] bg-white px-3 text-[12px] font-semibold text-[#111827]">
            {avatarBusy ? "Uploading..." : "Upload avatar"}
            <input
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) {
                  void uploadAvatar(file);
                }
              }}
            />
          </label>
        </div>
      </div>

      {error ? <p className="mt-4 text-[13px] text-[#b42318]">{error}</p> : null}

      <div className="mt-6 flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={() => {
            const fallback = String(profile?.username || form.username || "").trim();
            if (fallback) {
              onNavigate(`/creators/${encodeURIComponent(fallback)}`);
              return;
            }
            onNavigate("/marketplace");
          }}
          className="h-10 rounded-xl border border-black/[0.1] bg-white px-4 text-[13px] font-semibold text-[#111827]"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={saveProfile}
          disabled={saving}
          className="h-10 rounded-xl bg-[#111827] px-4 text-[13px] font-semibold text-white disabled:opacity-60"
        >
          {saving ? "Saving..." : isCreateMode ? "Create profile" : "Save changes"}
        </button>
      </div>
    </div>
  );
}
