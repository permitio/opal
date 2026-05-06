package access.authorization.context.verify.policy_0850

# Auto-generated policy 850 (Rego v1 syntax)
# Package: access.authorization.context.verify

# Metadata
metadata := {
    "policy_id": "0850",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0850_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0850_allowed if {
    data.policies.access.enabled
}
policy_0850_allowed if {
    input.user.role == "admin"
}
policy_0850_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
