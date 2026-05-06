package audit.authorization.resource.deny.policy_0582

# Auto-generated policy 582 (Rego v1 syntax)
# Package: audit.authorization.resource.deny

# Metadata
metadata := {
    "policy_id": "0582",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0582_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0582_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0582_allowed if {
    input.user.active
    input.resource.public
}
