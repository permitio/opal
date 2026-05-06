package access.authorization.context.verify.helpers.policy_0343

# Auto-generated policy 343 (Rego v1 syntax)
# Package: access.authorization.context.verify.helpers

# Metadata
metadata := {
    "policy_id": "0343",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0343_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0343_allowed if {
    input.user.role == "admin"
}
