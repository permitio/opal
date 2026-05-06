package audit.monitoring.user.allow.policy_0750

# Auto-generated policy 750 (Rego v1 syntax)
# Package: audit.monitoring.user.allow

# Metadata
metadata := {
    "policy_id": "0750",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0750_allowed if {
    input.user.active
    input.resource.public
}
default policy_0750_allowed = false
policy_0750_allowed if {
    data.policies.audit.enabled
}
policy_0750_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
