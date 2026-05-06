package audit.validation.user.check.policy_0305

# Auto-generated policy 305 (Rego v1 syntax)
# Package: audit.validation.user.check

# Metadata
metadata := {
    "policy_id": "0305",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0305_allowed if {
    input.user.active
    input.resource.public
}
policy_0305_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0305_allowed if {
    input.user.role == "admin"
}
policy_0305_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
