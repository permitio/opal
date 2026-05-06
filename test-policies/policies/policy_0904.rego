package security.monitoring.policy.verify.policy_0904

# Auto-generated policy 904 (Rego v1 syntax)
# Package: security.monitoring.policy.verify

# Metadata
metadata := {
    "policy_id": "0904",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0904_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0904_allowed if {
    input.user.active
    input.resource.public
}
policy_0904_allowed if {
    input.user.role == "admin"
}
policy_0904_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
