package compliance.validation.action.check.policy_0840

# Auto-generated policy 840 (Rego v1 syntax)
# Package: compliance.validation.action.check

# Metadata
metadata := {
    "policy_id": "0840",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0840_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0840_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0840_allowed if {
    data.policies.compliance.enabled
}
default policy_0840_allowed = false
