package security.enforcement.user.deny.policy_0633

# Auto-generated policy 633 (Rego v1 syntax)
# Package: security.enforcement.user.deny

# Metadata
metadata := {
    "policy_id": "0633",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0633_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0633_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0633_allowed if {
    input.user.active
    input.resource.public
}
