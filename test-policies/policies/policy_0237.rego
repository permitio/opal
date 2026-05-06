package compliance.validation.user.deny.policy_0237

# Auto-generated policy 237 (Rego v1 syntax)
# Package: compliance.validation.user.deny

# Metadata
metadata := {
    "policy_id": "0237",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0237_allowed if {
    input.user.active
    input.resource.public
}
policy_0237_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0237_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
