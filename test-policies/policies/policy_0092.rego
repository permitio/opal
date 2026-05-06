package access.authentication.resource.validate.data.policy_0092

# Auto-generated policy 92 (Rego v1 syntax)
# Package: access.authentication.resource.validate.data

# Metadata
metadata := {
    "policy_id": "0092",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0092_allowed if {
    input.user.active
    input.resource.public
}
policy_0092_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0092_allowed if {
    input.user.role == "admin"
}
