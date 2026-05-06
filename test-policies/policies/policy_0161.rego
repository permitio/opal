package compliance.validation.action.deny.policy_0161

# Auto-generated policy 161 (Rego v1 syntax)
# Package: compliance.validation.action.deny

# Metadata
metadata := {
    "policy_id": "0161",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0161_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0161_allowed if {
    input.user.active
    input.resource.public
}
policy_0161_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0161_allowed if {
    input.user.role == "admin"
}
