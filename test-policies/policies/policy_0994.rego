package access.authorization.user.verify.policy_0994

# Auto-generated policy 994 (Rego v1 syntax)
# Package: access.authorization.user.verify

# Metadata
metadata := {
    "policy_id": "0994",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0994_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0994_allowed if {
    input.user.active
    input.resource.public
}
policy_0994_allowed if {
    input.user.role == "admin"
}
policy_0994_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
