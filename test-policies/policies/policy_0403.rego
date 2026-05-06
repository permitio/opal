package compliance.monitoring.action.verify.data.policy_0403

# Auto-generated policy 403 (Rego v1 syntax)
# Package: compliance.monitoring.action.verify.data

# Metadata
metadata := {
    "policy_id": "0403",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0403_allowed if {
    input.user.role == "admin"
}
policy_0403_allowed if {
    input.user.active
    input.resource.public
}
policy_0403_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0403_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
