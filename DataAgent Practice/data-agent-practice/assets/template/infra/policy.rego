package nexo

import rego.v1

default allow := false

roles := {
  "analyst": {"domains": ["Sales", "Marketing", "Supply Chain", "Finance"], "actions": ["discover", "query", "export"]},
  "manager": {"domains": ["Sales"], "actions": ["discover", "query"]},
  "engineer": {"domains": ["Sales", "Marketing", "Supply Chain", "Finance"], "actions": ["discover", "query", "export", "execute"]},
  "steward": {"domains": ["Sales"], "actions": ["discover", "query", "govern"]},
}

allow if {
  input.subject.tenant in ["luma", "northstar"]
  role := roles[input.subject.persona]
  input.domain in role.domains
  input.action in role.actions
}
