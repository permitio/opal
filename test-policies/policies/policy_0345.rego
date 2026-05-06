package security.authorization.user.check.data.policy_0345

# Auto-generated policy 345 (Rego v1 syntax)
# Package: security.authorization.user.check.data

# Metadata
metadata := {
    "policy_id": "0345",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0345_allowed if {
    input.user.active
    input.resource.public
}
policy_0345_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0345_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
