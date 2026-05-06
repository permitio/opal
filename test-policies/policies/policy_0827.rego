package security.validation.policy.allow.core.policy_0827

# Auto-generated policy 827 (Rego v1 syntax)
# Package: security.validation.policy.allow.core

# Metadata
metadata := {
    "policy_id": "0827",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0827_allowed if {
    data.policies.security.enabled
}
policy_0827_allowed if {
    input.user.role == "admin"
}
policy_0827_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
