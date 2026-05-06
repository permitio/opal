package compliance.enforcement.resource.check.helpers.policy_0583

# Auto-generated policy 583 (Rego v1 syntax)
# Package: compliance.enforcement.resource.check.helpers

# Metadata
metadata := {
    "policy_id": "0583",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0583_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0583_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
