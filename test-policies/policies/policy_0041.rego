package compliance.monitoring.user.check.policy_0041

# Auto-generated policy 41 (Rego v1 syntax)
# Package: compliance.monitoring.user.check

# Metadata
metadata := {
    "policy_id": "0041",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0041_allowed if {
    input.user.active
    input.resource.public
}
policy_0041_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0041_allowed if {
    data.policies.compliance.enabled
}
policy_0041_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
