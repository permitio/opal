package security.validation.policy.deny.helpers.policy_0267

# Auto-generated policy 267 (Rego v1 syntax)
# Package: security.validation.policy.deny.helpers

# Metadata
metadata := {
    "policy_id": "0267",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0267_allowed if {
    input.user.active
    input.resource.public
}
policy_0267_allowed if {
    input.user.role == "admin"
}
policy_0267_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0267_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
