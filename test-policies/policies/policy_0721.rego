package compliance.monitoring.resource.check.data.policy_0721

# Auto-generated policy 721 (Rego v1 syntax)
# Package: compliance.monitoring.resource.check.data

# Metadata
metadata := {
    "policy_id": "0721",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0721_allowed if {
    input.user.active
    input.resource.public
}
policy_0721_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0721_allowed = false
policy_0721_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
