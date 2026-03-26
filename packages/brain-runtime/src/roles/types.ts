/**
 * Shared types for role definitions and personality profiles.
 */

export interface RoleDefinition {
  id: string;
  name: string;
  description: string;
  whenToUse: string;
  systemPrompt: string;
  defaultTraits: string[];
  avatarEmoji: string;
  avatarColor: string;
}

export interface PersonalityProfile {
  openers: string[];
  maxWords: number;
  directness: number;
  expressiveness: number;
  vocabulary: string[];
  disagreementStyle: string;
  agreementStyle: string;
  quickResponse: string;
}

export interface AgentRole {
  role: RoleDefinition;
  personality: PersonalityProfile;
}