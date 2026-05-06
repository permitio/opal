package security.authorization.policy.verify.logic.policy_0440

# Auto-generated policy 440 (Rego v1 syntax)
# Package: security.authorization.policy.verify.logic

# Metadata
metadata := {
    "policy_id": "0440",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0440_allowed if {
    input.user.role == "admin"
}
policy_0440_allowed if {
    input.user.active
    input.resource.public
}
policy_0440_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0440_allowed if {
    data.policies.security.enabled
}
