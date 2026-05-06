package access.authentication.user.deny.helpers.policy_0250

# Auto-generated policy 250 (Rego v1 syntax)
# Package: access.authentication.user.deny.helpers

# Metadata
metadata := {
    "policy_id": "0250",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0250_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0250_allowed if {
    input.user.active
    input.resource.public
}
policy_0250_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
