export async function fetchAgentStatus(agentName: string) {
  const res = await fetch(`http://localhost:8000/api/v1/agents/${agentName}`);
  if (!res.ok) throw new Error('Failed to fetch agent status');
  return res.json();
}

export async function fetchAgentConfig(agentName: string) {
  const res = await fetch(`http://localhost:8000/api/v1/agents/${agentName}/config`);
  if (!res.ok) throw new Error('Failed to fetch agent config');
  return res.json();
}

export async function updateAgentConfig(agentName: string, config: any) {
  const res = await fetch(`http://localhost:8000/api/v1/agents/${agentName}/config`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
  if (!res.ok) throw new Error('Failed to update agent config');
  return res.json();
}

export async function pauseAgent(agentName: string) {
  const res = await fetch(`http://localhost:8000/api/v1/agents/${agentName}/pause`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error('Failed to pause agent');
  return res.json();
}

export async function resumeAgent(agentName: string) {
  const res = await fetch(`http://localhost:8000/api/v1/agents/${agentName}/resume`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error('Failed to resume agent');
  return res.json();
}
