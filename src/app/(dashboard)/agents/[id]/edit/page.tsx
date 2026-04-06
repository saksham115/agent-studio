"use client";

import { useParams } from "next/navigation";
import { WizardShell } from "@/components/agent-wizard/wizard-shell";

export default function EditAgentPage() {
  const params = useParams();
  const agentId = params.id as string;

  return <WizardShell agentId={agentId} />;
}
