import { useEffect, useMemo, useState } from "react";

import {
  followCreator,
  getCreatorProfile,
  getMyCreatorProfile,
  listCreatorActivity,
  listCreatorAgents,
  listCreatorTeams,
  unfollowCreator,
  type CreatorProfileRecord,
  type MarketplaceWorkflowRecord,
} from "../../../api/client";
import { ConnectorBrandIcon } from "../../components/connectors/ConnectorBrandIcon";
import { resolveAgentIconConnectorId } from "../../utils/agentIconResolver";

type CreatorProfilePageProps = {
  username: string;
  onNavigate: (path: string) => void;
};

export function CreatorProfilePage({ username, onNavigate }: CreatorProfilePageProps) {
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [profile, setProfile] = useState<CreatorProfileRecord | null>(null);
  const [myProfile, setMyProfile] = useState<CreatorProfileRecord | null>(null);
  const [agents, setAgents] = useState<Array<Record<string, unknown>>>([]);
  const [teams, setTeams] = useState<MarketplaceWorkflowRecord[]>([]);
  const [activity, setActivity] = useState<Array<Record<string, unknown>>>([]);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const [creator, mine, creatorAgents, creatorTeams, creatorActivity] = await Promise.all([
          getCreatorProfile(username),
          getMyCreatorProfile().catch(() => ({ exists: false } as CreatorProfileRecord & { exists?: boolean })),
          listCreatorAgents(username),
          listCreatorTeams(username, 24),
          listCreatorActivity(username, 20),
        ]);
        setProfile(creator);
        setMyProfile(mine?.exists ? mine : null);
        setAgents(creatorAgents || []);
        setTeams(creatorTeams || []);
        setActivity(creatorActivity || []);
      } catch (nextError) {
        setError(String(nextError || "Failed to load creator profile."));
      } finally {
        setLoading(false);
      }
    };
    if (!username) {
      setError("Missing creator username.");
      setLoading(false);
      return;
    }
    void load();
  }, [username]);

  const isOwnProfile = useMemo(() => {
    if (!profile?.username || !myProfile?.username) {
      return false;
    }
    return profile.username.toLowerCase() === myProfile.username.toLowerCase();
  }, [profile?.username, myProfile?.username]);

  const toggleFollow = async () => {
    if (!profile?.username || isOwnProfile) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      if (profile.is_following) {
        await unfollowCreator(profile.username);
        setProfile({ ...profile, is_following: false, follower_count: Math.max(0, profile.follower_count - 1) });
      } else {
        await followCreator(profile.username);
        setProfile({ ...profile, is_following: true, follower_count: profile.follower_count + 1 });
      }
    } catch (nextError) {
      setError(String(nextError || "Failed to update follow status."));
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return <p className="text-[14px] text-[#64748b]">Loading creator profile...</p>;
  }
  if (error) {
    return <p className="text-[14px] text-[#b42318]">{error}</p>;
  }
  if (!profile) {
    return <p className="text-[14px] text-[#64748b]">Creator not found.</p>;
  }

  return (
    <div className="space-y-6">
      <section className="rounded-[24px] border border-black/[0.08] bg-white p-6 shadow-[0_16px_32px_rgba(15,23,42,0.08)]">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-center gap-4">
            <div className="h-16 w-16 overflow-hidden rounded-2xl bg-[#eef2ff]">
              {profile.avatar_url ? (
                <img src={profile.avatar_url} alt={profile.display_name || profile.username} className="h-full w-full object-cover" />
              ) : null}
            </div>
            <div>
              <h1 className="text-[30px] font-semibold tracking-[-0.03em] text-[#111827]">
                {profile.display_name || profile.username}
              </h1>
              <p className="text-[14px] text-[#667085]">@{profile.username}</p>
            </div>
          </div>
          {isOwnProfile ? (
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => onNavigate("/creators/me/dashboard")}
                className="h-10 rounded-xl border border-black/[0.1] bg-white px-4 text-[13px] font-semibold text-[#111827]"
              >
                Dashboard
              </button>
              <button
                type="button"
                onClick={() => onNavigate("/creators/me/edit")}
                className="h-10 rounded-xl border border-black/[0.1] bg-white px-4 text-[13px] font-semibold text-[#111827]"
              >
                Edit Profile
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={toggleFollow}
              disabled={busy}
              className={`h-10 rounded-xl px-4 text-[13px] font-semibold transition ${
                profile.is_following ? "border border-[#bbf7d0] bg-[#ecfdf3] text-[#166534]" : "bg-[#111827] text-white"
              }`}
            >
              {profile.is_following ? "Following" : "Follow"}
            </button>
          )}
        </div>
        <p className="mt-4 text-[14px] leading-6 text-[#334155]">{profile.bio || "No bio added yet."}</p>
        <div className="mt-4 flex flex-wrap gap-2 text-[12px] text-[#475467]">
          <span className="rounded-full bg-[#eef2ff] px-3 py-1">{profile.follower_count} followers</span>
          <span className="rounded-full bg-[#eef2ff] px-3 py-1">{profile.published_agent_count} agents</span>
          <span className="rounded-full bg-[#eef2ff] px-3 py-1">{profile.published_team_count} teams</span>
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        <div className="space-y-6">
          <div className="rounded-[22px] border border-black/[0.08] bg-white p-5">
            <h2 className="text-[18px] font-semibold text-[#111827]">Published Agents</h2>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              {agents.length ? (
                agents.slice(0, 8).map((row) => {
                  const agentId = String(row.agent_id || row.id || "").trim();
                  const iconConnectorId = resolveAgentIconConnectorId({
                    required_connectors: row.required_connectors,
                    connector_status: row.connector_status,
                    has_computer_use: row.has_computer_use,
                    category: row.category,
                    tags: row.tags,
                  });
                  return (
                    <button
                      key={agentId}
                      type="button"
                      onClick={() => onNavigate(`/marketplace/agents/${encodeURIComponent(agentId)}`)}
                      className="rounded-xl border border-black/[0.08] bg-[#f8fafc] p-3 text-left transition hover:bg-[#eef2ff]"
                    >
                      <div className="flex items-center gap-2">
                        <ConnectorBrandIcon
                          connectorId={iconConnectorId}
                          label={String(row.name || agentId)}
                          size={18}
                        />
                        <p className="text-[13px] font-semibold text-[#111827]">{String(row.name || agentId)}</p>
                      </div>
                      <p className="mt-1 line-clamp-2 text-[12px] text-[#667085]">{String(row.description || "")}</p>
                    </button>
                  );
                })
              ) : (
                <p className="text-[13px] text-[#667085]">No published agents yet.</p>
              )}
            </div>
          </div>

          <div className="rounded-[22px] border border-black/[0.08] bg-white p-5">
            <h2 className="text-[18px] font-semibold text-[#111827]">Published Teams</h2>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              {teams.length ? (
                teams.slice(0, 8).map((row) => (
                  <button
                    key={row.slug}
                    type="button"
                    onClick={() => onNavigate(`/marketplace/teams/${encodeURIComponent(row.slug)}`)}
                    className="rounded-xl border border-black/[0.08] bg-[#f8fafc] p-3 text-left transition hover:bg-[#eef2ff]"
                  >
                    <p className="text-[13px] font-semibold text-[#111827]">{row.name}</p>
                    <p className="mt-1 line-clamp-2 text-[12px] text-[#667085]">{row.description}</p>
                  </button>
                ))
              ) : (
                <p className="text-[13px] text-[#667085]">No published teams yet.</p>
              )}
            </div>
          </div>
        </div>

        <div className="rounded-[22px] border border-black/[0.08] bg-white p-5">
          <h2 className="text-[18px] font-semibold text-[#111827]">Recent Activity</h2>
          <div className="mt-3 space-y-2">
            {activity.length ? (
              activity.map((item) => (
                <div key={String(item.id || Math.random())} className="rounded-xl border border-black/[0.08] bg-[#f8fafc] px-3 py-2">
                  <p className="text-[13px] font-semibold text-[#111827]">{String(item.title || item.event_type || "Update")}</p>
                  <p className="text-[12px] text-[#667085]">{String(item.summary || "")}</p>
                </div>
              ))
            ) : (
              <p className="text-[13px] text-[#667085]">No activity yet.</p>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
