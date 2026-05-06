package governance.validation.user.validate.policy_0459

# Auto-generated policy 459 (Rego v1 syntax)
# Package: governance.validation.user.validate

# Metadata
metadata := {
    "policy_id": "0459",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0459_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0459_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0459_allowed if {
    data.policies.governance.enabled
}
