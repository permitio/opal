package access.enforcement.action.allow.policy_0748

# Auto-generated policy 748 (Rego v1 syntax)
# Package: access.enforcement.action.allow

# Metadata
metadata := {
    "policy_id": "0748",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0748_allowed if {
    data.policies.access.enabled
}
policy_0748_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
