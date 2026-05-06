package compliance.authorization.policy.validate.policy_0975

# Auto-generated policy 975 (Rego v1 syntax)
# Package: compliance.authorization.policy.validate

# Metadata
metadata := {
    "policy_id": "0975",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0975_allowed if {
    input.user.active
    input.resource.public
}
policy_0975_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0975_allowed if {
    input.user.role == "admin"
}
policy_0975_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
