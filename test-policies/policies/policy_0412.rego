package compliance.validation.user.deny.logic.policy_0412

# Auto-generated policy 412 (Rego v1 syntax)
# Package: compliance.validation.user.deny.logic

# Metadata
metadata := {
    "policy_id": "0412",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0412_allowed = false
policy_0412_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0412_allowed if {
    input.user.active
    input.resource.public
}
policy_0412_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
