package security.authentication.action.check.policy_0088

# Auto-generated policy 88 (Rego v1 syntax)
# Package: security.authentication.action.check

# Metadata
metadata := {
    "policy_id": "0088",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0088_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0088_allowed if {
    data.policies.security.enabled
}
