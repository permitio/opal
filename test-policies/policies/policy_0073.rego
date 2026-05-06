package access.validation.resource.verify.policy_0073

# Auto-generated policy 73 (Rego v1 syntax)
# Package: access.validation.resource.verify

# Metadata
metadata := {
    "policy_id": "0073",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0073_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0073_allowed if {
    input.user.active
    input.resource.public
}
policy_0073_allowed if {
    input.user.role == "admin"
}
policy_0073_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
