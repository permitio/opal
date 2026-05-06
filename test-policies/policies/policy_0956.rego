package access.authentication.action.check.core.policy_0956

# Auto-generated policy 956 (Rego v1 syntax)
# Package: access.authentication.action.check.core

# Metadata
metadata := {
    "policy_id": "0956",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0956_allowed = false
policy_0956_allowed if {
    data.policies.access.enabled
}
policy_0956_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0956_allowed if {
    input.user.role == "admin"
}
