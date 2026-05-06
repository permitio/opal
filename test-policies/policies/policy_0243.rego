package access.authentication.policy.validate.logic.policy_0243

# Auto-generated policy 243 (Rego v1 syntax)
# Package: access.authentication.policy.validate.logic

# Metadata
metadata := {
    "policy_id": "0243",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0243_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0243_allowed if {
    input.user.role == "admin"
}
policy_0243_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0243_allowed if {
    input.user.active
    input.resource.public
}
