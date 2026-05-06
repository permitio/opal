package audit.authorization.context.allow.policy_0040

# Auto-generated policy 40 (Rego v1 syntax)
# Package: audit.authorization.context.allow

# Metadata
metadata := {
    "policy_id": "0040",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0040_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0040_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0040_allowed if {
    data.policies.audit.enabled
}
default policy_0040_allowed = false
