package risk.monitoring.action.deny.policy_0629

# Auto-generated policy 629 (Rego v1 syntax)
# Package: risk.monitoring.action.deny

# Metadata
metadata := {
    "policy_id": "0629",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0629_allowed if {
    data.policies.risk.enabled
}
policy_0629_allowed if {
    input.user.active
    input.resource.public
}
default policy_0629_allowed = false
