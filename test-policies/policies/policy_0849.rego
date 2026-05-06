package security.authorization.policy.verify.policy_0849

# Auto-generated policy 849 (Rego v1 syntax)
# Package: security.authorization.policy.verify

# Metadata
metadata := {
    "policy_id": "0849",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0849_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0849_allowed if {
    data.policies.security.enabled
}
